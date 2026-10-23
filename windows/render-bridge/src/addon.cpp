#include <reshade.hpp>
#include <bcrypt.h>
#include "trace_model.hpp"
#include <array>
#include <filesystem>
#include <fstream>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>
#include <tuple>
#include <unordered_map>

static_assert(RESHADE_API_VERSION == 20, "Build with the pinned ReShade SDK");
namespace api = reshade::api;
using forge::trace::Handle;
using forge::trace::Descriptor;
using forge::trace::Slot;
using forge::trace::quote;

namespace {
constexpr std::size_t max_objects = 65536;
constexpr std::size_t max_pipelines = 32768;
constexpr std::size_t max_commands = 512;
struct Range { std::uint32_t binding, count, reg, space, type; };
using Layout = std::vector<std::vector<Range>>;
struct Pipeline { std::string pixel, compute; };
struct Bound {
    Handle layout = 0;
    std::string shader;
    std::map<std::uint32_t, Handle> tables;
    std::map<std::pair<std::uint32_t, std::uint32_t>, Descriptor> pushed;
    void use(Handle value) { if (layout != value) { tables.clear(); pushed.clear(); layout = value; } }
};
struct Command { Bound graphics, compute; std::vector<std::uint64_t> targets; std::uint64_t depth = 0; };
struct Mapping { const std::byte *data; std::uint64_t offset, size; };
struct Device {
    std::mutex mutex;
    forge::trace::Ledger ledger;
    std::map<Handle, Pipeline> pipelines;
    std::map<Handle, Layout> layouts;
    std::map<api::command_list *, Command> commands;
    std::map<api::swapchain *, std::vector<Handle>> backbuffers;
    std::map<Handle, Mapping> mapped;
    std::vector<std::string> events, constants;
    std::set<std::uint64_t> referenced;
    std::set<std::tuple<std::uint64_t, std::uint64_t, std::uint64_t>> sampled;
    std::uint64_t frame = 0, capture_start = 0, serial = 0, dropped = 0, range_samples = 0;
    std::uint32_t width = 0, height = 0, remaining = 0;
    bool capturing = false, auto_done = false, key_down = false;
};
std::mutex devices_mutex;
std::unordered_map<api::device *, std::shared_ptr<Device>> devices;
std::filesystem::path config_path;
HMODULE addon_module = nullptr;
std::once_flag config_once;
unsigned auto_frame = 180, capture_frames = 2, max_events = 4096;

std::string hex(Handle n) { std::ostringstream s; s << "0x" << std::hex << n; return s.str(); }
std::string utf8(const std::wstring &s) {
    if (s.empty()) return {};
    const int n = WideCharToMultiByte(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), nullptr, 0, nullptr, nullptr);
    std::string out(n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), out.data(), n, nullptr, nullptr);
    return out;
}
std::string fingerprint(const api::shader_desc &shader) {
    if (!shader.code || !shader.code_size || shader.code_size > ULONG_MAX) return {};
    std::array<unsigned char, 32> digest{};
    if (BCryptHash(BCRYPT_SHA256_ALG_HANDLE, nullptr, 0,
                   static_cast<PUCHAR>(const_cast<void *>(shader.code)), static_cast<ULONG>(shader.code_size),
                   digest.data(), static_cast<ULONG>(digest.size())) < 0) return {};
    constexpr char chars[] = "0123456789abcdef";
    std::string result;
    for (const auto c : digest) { result += chars[c >> 4]; result += chars[c & 15]; }
    return result;
}
std::shared_ptr<Device> state(api::device *device) {
    std::lock_guard lock(devices_mutex);
    const auto it = devices.find(device);
    return it == devices.end() ? nullptr : it->second;
}
template<class F> void observe(api::device *device, F &&f) noexcept {
    try { if (const auto d = state(device)) { std::lock_guard lock(d->mutex); f(*d); } }
    catch (...) { reshade::log::message(reshade::log::level::error, "rtxForge renderer diagnostic observation failed; original rendering continues."); }
}
Slot slot(api::device *device, api::descriptor_table table, std::uint32_t binding, std::uint32_t array = 0) {
    api::descriptor_heap heap{}; std::uint32_t offset = 0;
    device->get_descriptor_heap_offset(table, binding, array, &heap, &offset);
    return {heap.handle, offset};
}
Descriptor descriptor(Device &d, const api::descriptor_table_update &u, std::uint32_t i) {
    Descriptor result; result.type = static_cast<std::uint32_t>(u.type);
    switch (u.type) {
    case api::descriptor_type::shader_resource_view:
    case api::descriptor_type::unordered_access_view:
        result.resource_id = d.ledger.resolve_view(static_cast<const api::resource_view *>(u.descriptors)[i].handle); break;
    case api::descriptor_type::sampler_with_resource_view:
        result.resource_id = d.ledger.resolve_view(static_cast<const api::sampler_with_resource_view *>(u.descriptors)[i].view.handle); break;
    case api::descriptor_type::constant_buffer: {
        const auto &b = static_cast<const api::buffer_range *>(u.descriptors)[i];
        result.resource_id = d.ledger.resolve(b.buffer.handle); result.offset = b.offset; result.size = b.size; break;
    }
    default: break;
    }
    return result;
}
void sample_constants(Device &d, const Descriptor &b) {
    if (b.type != static_cast<unsigned>(api::descriptor_type::constant_buffer) || !d.ledger.alive(b.resource_id)
        || d.constants.size() >= 128 || !d.sampled.emplace(d.frame, b.resource_id, b.offset).second) return;
    const auto &r = d.ledger.resources.at(b.resource_id);
    const auto it = d.mapped.find(r.handle);
    if (it == d.mapped.end() || b.offset < it->second.offset || b.offset >= r.width) return;
    const auto relative = b.offset - it->second.offset;
    if (relative >= it->second.size) return;
    const auto bytes = std::min<std::uint64_t>({1024, b.size, r.width - b.offset, it->second.size - relative});
    std::array<unsigned char, 1024> data{}; SIZE_T read = 0;
    if (!bytes || !ReadProcessMemory(GetCurrentProcess(), it->second.data + relative, data.data(), static_cast<SIZE_T>(bytes), &read) || read != bytes) return;
    constexpr char chars[] = "0123456789abcdef";
    std::string encoded;
    for (SIZE_T i = 0; i < read; ++i) { encoded += chars[data[i] >> 4]; encoded += chars[data[i] & 15]; }
    d.constants.push_back("{\"resource\":" + std::to_string(b.resource_id) + ",\"offset\":" + std::to_string(b.offset)
        + ",\"frame\":" + std::to_string(d.frame) + ",\"bytes_hex\":" + quote(encoded) + "}");
}
void emit_descriptor(Device &d, std::ostringstream &s, const Descriptor &b, unsigned param, unsigned binding, bool &first) {
    if (!first) s << ','; first = false;
    s << "{\"param\":" << param << ",\"binding\":" << binding << ",\"type\":" << b.type
      << ",\"resource\":" << b.resource_id << ",\"alive\":" << (d.ledger.alive(b.resource_id) ? "true" : "false")
      << ",\"offset\":" << b.offset << ",\"size\":" << quote(std::to_string(b.size)) << '}';
    if (b.resource_id) d.referenced.insert(b.resource_id);
    sample_constants(d, b);
}
void record(api::command_list *cmd, const char *kind, bool compute) {
    observe(cmd->get_device(), [&](Device &d) {
        if (!d.capturing) return;
        if (d.events.size() >= max_events) { ++d.dropped; return; }
        const auto ci = d.commands.find(cmd);
        if (ci == d.commands.end()) { ++d.dropped; return; }
        auto &c = ci->second; auto &b = compute ? c.compute : c.graphics;
        std::ostringstream s;
        s << "{\"kind\":" << quote(kind) << ",\"frame\":" << d.frame << ",\"command_list\":" << quote(hex(reinterpret_cast<Handle>(cmd)))
          << ",\"shader_sha256\":" << quote(b.shader) << ",\"depth\":" << c.depth << ",\"targets\":[";
        for (std::size_t i = 0; i < c.targets.size(); ++i) { if (i) s << ','; s << c.targets[i]; d.referenced.insert(c.targets[i]); }
        d.referenced.insert(c.depth); s << "],\"descriptors\":[";
        bool first = true;
        for (const auto &[key, value] : b.pushed) emit_descriptor(d, s, value, key.first, key.second, first);
        const auto layout = d.layouts.find(b.layout);
        unsigned emitted = 0;
        if (layout != d.layouts.end()) for (const auto &[param, table] : b.tables) {
            if (param >= layout->second.size()) continue;
            for (const auto &range : layout->second[param]) {
                const auto count = std::min(range.count, 64u);
                if (range.count > count) ++d.range_samples;
                for (unsigned i = 0; i < count && emitted < 128; ++i, ++emitted) {
                    if (range.binding > UINT32_MAX - i) break;
                    const auto value = d.ledger.get(slot(cmd->get_device(), {table}, range.binding + i));
                    emit_descriptor(d, s, value, param, range.binding + i, first);
                }
                if (emitted >= 128) { ++d.range_samples; break; }
            }
        }
        s << "]}"; d.events.push_back(s.str());
    });
}
void write_capture(const Device &d) {
    wchar_t folder[32768]{};
    const auto length = GetEnvironmentVariableW(L"LOCALAPPDATA", folder, static_cast<DWORD>(std::size(folder)));
    if (!length || length >= std::size(folder)) return;
    const auto output = std::filesystem::path(folder) / L"rtxForge" / L"diagnostics" / L"render-bridge" / std::to_wstring(GetCurrentProcessId());
    std::filesystem::create_directories(output);
    wchar_t exe[32768]{}; GetModuleFileNameW(nullptr, exe, static_cast<DWORD>(std::size(exe)));
    WIN32_FILE_ATTRIBUTE_DATA attributes{}; GetFileAttributesExW(exe, GetFileExInfoStandard, &attributes);
    const auto size = (static_cast<std::uint64_t>(attributes.nFileSizeHigh) << 32) | attributes.nFileSizeLow;
    const auto file = output / (L"capture-" + std::to_wstring(d.serial) + L"-" + std::to_wstring(d.capture_start) + L".json");
    std::ofstream s(file, std::ios::binary | std::ios::trunc);
    if (!s) throw std::runtime_error("Diagnostic report could not be opened");
    s << "{\"schema\":1,\"stage\":\"diagnostic\",\"api\":\"d3d12\",\"sr_enabled\":false,\"fg_enabled\":false,"
         "\"ordering\":\"cpu-command-recording-order\",\"gpu_execution_order_verified\":false,"
         "\"motion_vectors_verified\":false,\"jitter_verified\":false,\"hud_boundary_verified\":false,"
         "\"sdk_commit\":\"18deaa52de0c425a78b329e9cb3c497281cd00ec\",\"pid\":" << GetCurrentProcessId()
      << ",\"executable\":" << quote(utf8(exe)) << ",\"executable_size\":" << size
      << ",\"capture_start\":" << d.capture_start << ",\"capture_end\":" << d.frame
      << ",\"output_width\":" << d.width << ",\"output_height\":" << d.height
      << ",\"dropped_events\":" << d.dropped << ",\"catalog_drops\":" << d.ledger.dropped
      << ",\"sampled_descriptor_ranges\":" << d.range_samples << ",\"resources\":[";
    bool first = true;
    for (const auto id : d.referenced) {
        const auto it = d.ledger.resources.find(id); if (it == d.ledger.resources.end()) continue;
        const auto &r = it->second; if (!first) s << ','; first = false;
        s << "{\"id\":" << r.id << ",\"handle\":" << quote(hex(r.handle)) << ",\"width\":" << r.width << ",\"height\":" << r.height
          << ",\"format\":" << r.format << ",\"usage\":" << r.usage << ",\"alive\":" << (r.alive ? "true" : "false") << '}';
    }
    s << "],\"events\":[";
    for (std::size_t i = 0; i < d.events.size(); ++i) { if (i) s << ','; s << d.events[i]; }
    s << "],\"constant_buffer_samples\":[";
    for (std::size_t i = 0; i < d.constants.size(); ++i) { if (i) s << ','; s << d.constants[i]; }
    s << "]}\n"; s.flush();
    if (!s) throw std::runtime_error("Diagnostic report write failed");
    reshade::log::message(reshade::log::level::info, ("rtxForge diagnostic capture: " + utf8(file.wstring())).c_str());
}

void on_device(api::device *device) {
    reshade::log::message(reshade::log::level::info, "rtxForge diagnostic init_device callback entered.");
    if (device->get_api() != api::device_api::d3d12) return;
    std::call_once(config_once, [] {
        // Configuration I/O and path allocation must happen outside the DLL loader lock.
        std::wstring path(32768, L'\0');
        const auto n = GetModuleFileNameW(addon_module, path.data(), static_cast<DWORD>(path.size()));
        if (!n || n >= path.size()) return;
        path.resize(n);
        config_path = std::filesystem::path(path).parent_path() / L"rtxforge-render-bridge.ini";
        auto_frame = GetPrivateProfileIntW(L"Capture", L"AutoFrame", 180, config_path.c_str());
        capture_frames = std::clamp(GetPrivateProfileIntW(L"Capture", L"Frames", 2, config_path.c_str()), 1u, 4u);
        max_events = std::clamp(GetPrivateProfileIntW(L"Capture", L"MaxEvents", 4096, config_path.c_str()), 64u, 8192u);
    });
    std::lock_guard lock(devices_mutex); devices[device] = std::make_shared<Device>();
    reshade::log::message(reshade::log::level::info, "rtxForge independent D3D12 diagnostic attached. SR/FG are not implemented.");
}
void on_destroy_device(api::device *device) { std::lock_guard lock(devices_mutex); devices.erase(device); }
void on_resource(api::device *device, const api::resource_desc &r, const api::subresource_data *, api::resource_usage, api::resource value) {
    observe(device, [&](Device &d) { d.ledger.create(value.handle, r.type == api::resource_type::buffer ? r.buffer.size : r.texture.width,
        r.type == api::resource_type::buffer ? 0 : r.texture.height, r.type == api::resource_type::buffer ? 0 : static_cast<unsigned>(r.texture.format), static_cast<unsigned>(r.usage)); });
}
void on_destroy_resource(api::device *device, api::resource r) { observe(device, [&](Device &d) { d.ledger.destroy(r.handle); d.mapped.erase(r.handle); }); }
void on_view(api::device *device, api::resource r, api::resource_usage, const api::resource_view_desc &, api::resource_view v) {
    observe(device, [&](Device &d) {
        // Swapchain resources need not emit init_resource. A view is independent evidence
        // that this resource is alive; add it without inventing a creation observation.
        if (r.handle && !d.ledger.resolve(r.handle)) {
            const auto desc = device->get_resource_desc(r);
            d.ledger.create(r.handle, desc.type == api::resource_type::buffer ? desc.buffer.size : desc.texture.width,
                desc.type == api::resource_type::buffer ? 0 : desc.texture.height,
                desc.type == api::resource_type::buffer ? 0 : static_cast<unsigned>(desc.texture.format), static_cast<unsigned>(desc.usage));
        }
        if (d.ledger.views.size() < max_objects) d.ledger.view(v.handle, r.handle); else ++d.ledger.dropped;
    });
}
void on_destroy_view(api::device *device, api::resource_view v) { observe(device, [&](Device &d) { d.ledger.views.erase(v.handle); }); }
void on_pipeline(api::device *device, api::pipeline_layout, unsigned count, const api::pipeline_subobject *objects, api::pipeline value) {
    observe(device, [&](Device &d) {
        if (d.pipelines.size() >= max_pipelines) { ++d.ledger.dropped; return; }
        Pipeline p;
        for (unsigned i = 0; i < count; ++i) if (objects[i].count && objects[i].data) {
            if (objects[i].type == api::pipeline_subobject_type::pixel_shader) p.pixel = fingerprint(*static_cast<const api::shader_desc *>(objects[i].data));
            if (objects[i].type == api::pipeline_subobject_type::compute_shader) p.compute = fingerprint(*static_cast<const api::shader_desc *>(objects[i].data));
        }
        d.pipelines[value.handle] = std::move(p);
    });
}
void on_destroy_pipeline(api::device *device, api::pipeline p) { observe(device, [&](Device &d) { d.pipelines.erase(p.handle); }); }
void on_layout(api::device *device, unsigned count, const api::pipeline_layout_param *params, api::pipeline_layout layout) {
    observe(device, [&](Device &d) {
        if (count > 64 || d.layouts.size() >= max_objects) { ++d.ledger.dropped; return; }
        Layout out(count);
        for (unsigned i = 0; i < count; ++i) {
            const auto add = [&](const auto &r) { out[i].push_back({r.binding, r.count, r.dx_register_index, r.dx_register_space, static_cast<unsigned>(r.type)}); };
            const auto &p = params[i];
            if (p.type == api::pipeline_layout_param_type::descriptor_table) {
                for (unsigned j = 0; j < std::min(p.descriptor_table.count, 256u); ++j) add(p.descriptor_table.ranges[j]);
            } else if (p.type == api::pipeline_layout_param_type::descriptor_table_with_flags) {
                for (unsigned j = 0; j < std::min(p.descriptor_table_with_flags.count, 256u); ++j) add(p.descriptor_table_with_flags.ranges[j]);
            }
        }
        d.layouts[layout.handle] = std::move(out);
    });
}
void on_destroy_layout(api::device *device, api::pipeline_layout layout) { observe(device, [&](Device &d) { d.layouts.erase(layout.handle); }); }
bool on_update(api::device *device, unsigned count, const api::descriptor_table_update *updates) {
    observe(device, [&](Device &d) { for (unsigned n = 0; n < count; ++n) {
        const auto &u = updates[n];
        if (!u.descriptors || u.count > 4096 || u.binding > UINT32_MAX - u.count) { ++d.ledger.dropped; continue; }
        for (unsigned i = 0; i < u.count; ++i) d.ledger.put(slot(device, u.table, u.binding + i, u.array_offset), descriptor(d, u, i));
    } }); return false;
}
bool on_copy(api::device *device, unsigned count, const api::descriptor_table_copy *copies) {
    observe(device, [&](Device &d) { for (unsigned n = 0; n < count; ++n) { const auto &c = copies[n];
        d.ledger.copy(slot(device, c.source_table, c.source_binding, c.source_array_offset), slot(device, c.dest_table, c.dest_binding, c.dest_array_offset), c.count);
    } }); return false;
}
void on_init_command(api::command_list *cmd) { observe(cmd->get_device(), [&](Device &d) { if (d.commands.size() < max_commands) d.commands[cmd] = {}; else ++d.ledger.dropped; }); }
void on_destroy_command(api::command_list *cmd) { observe(cmd->get_device(), [&](Device &d) { d.commands.erase(cmd); }); }
void on_reset(api::command_list *cmd) { observe(cmd->get_device(), [&](Device &d) { if (d.commands.contains(cmd)) d.commands[cmd] = {}; }); }
void on_bind_pipeline(api::command_list *cmd, api::pipeline_stage stages, api::pipeline p) {
    observe(cmd->get_device(), [&](Device &d) { const auto ci = d.commands.find(cmd); if (ci == d.commands.end()) return;
        const auto it = d.pipelines.find(p.handle);
        if (static_cast<unsigned>(stages & api::pipeline_stage::pixel_shader)) ci->second.graphics.shader = it == d.pipelines.end() ? "" : it->second.pixel;
        if (static_cast<unsigned>(stages & api::pipeline_stage::compute_shader)) ci->second.compute.shader = it == d.pipelines.end() ? "" : it->second.compute;
    });
}
void targets(Device &d, Command &c, unsigned count, const api::resource_view *views, api::resource_view depth) {
    c.targets.clear(); for (unsigned i = 0; i < std::min(count, 8u); ++i) c.targets.push_back(d.ledger.resolve_view(views[i].handle));
    c.depth = d.ledger.resolve_view(depth.handle);
}
void on_targets(api::command_list *cmd, unsigned count, const api::resource_view *views, api::resource_view depth) {
    observe(cmd->get_device(), [&](Device &d) { if (auto it = d.commands.find(cmd); it != d.commands.end()) targets(d, it->second, count, views, depth); });
}
bool on_render_pass(api::command_list *cmd, unsigned count, const api::render_pass_render_target_desc *rt, const api::render_pass_depth_stencil_desc *ds, api::render_pass_flags) {
    std::array<api::resource_view, 8> views{}; for (unsigned i = 0; i < std::min(count, 8u); ++i) views[i] = rt[i].view;
    on_targets(cmd, std::min(count, 8u), views.data(), ds ? ds->view : api::resource_view{}); return false;
}
template<class F> void bound_stages(Command &c, api::shader_stage stages, F &&f) {
    if (static_cast<unsigned>(stages & api::shader_stage::all_graphics)) f(c.graphics);
    if (static_cast<unsigned>(stages & api::shader_stage::compute)) f(c.compute);
}
void on_tables(api::command_list *cmd, api::shader_stage stages, api::pipeline_layout layout, unsigned first, unsigned count, const api::descriptor_table *tables, unsigned, const unsigned *) {
    observe(cmd->get_device(), [&](Device &d) { const auto it = d.commands.find(cmd); if (it == d.commands.end() || first > 64 || count > 64 - first) return;
        bound_stages(it->second, stages, [&](Bound &b) { b.use(layout.handle); for (unsigned i = 0; i < count; ++i) b.tables[first + i] = tables[i].handle; });
    });
}
void on_push(api::command_list *cmd, api::shader_stage stages, api::pipeline_layout layout, unsigned param, const api::descriptor_table_update &u) {
    observe(cmd->get_device(), [&](Device &d) { const auto it = d.commands.find(cmd); if (it == d.commands.end() || param >= 64 || !u.descriptors || u.count > 128 || u.binding > UINT32_MAX - u.count) return;
        bound_stages(it->second, stages, [&](Bound &b) { b.use(layout.handle); for (unsigned i = 0; i < u.count; ++i) b.pushed[{param, u.binding + i}] = descriptor(d, u, i); });
    });
}
void on_map(api::device *device, api::resource r, std::uint64_t offset, std::uint64_t size, api::map_access, void **data) {
    observe(device, [&](Device &d) { if (!data || !*data || !d.ledger.resolve(r.handle)) return;
        const auto width = d.ledger.resources.at(d.ledger.resolve(r.handle)).width;
        if (offset < width) d.mapped[r.handle] = {static_cast<const std::byte *>(*data), offset, std::min(size, width - offset)};
    });
}
void on_unmap(api::device *device, api::resource r) { observe(device, [&](Device &d) { d.mapped.erase(r.handle); }); }
bool on_draw(api::command_list *c, unsigned, unsigned, unsigned, unsigned) { record(c, "draw", false); return false; }
bool on_draw_indexed(api::command_list *c, unsigned, unsigned, unsigned, int, unsigned) { record(c, "draw_indexed", false); return false; }
bool on_dispatch(api::command_list *c, unsigned, unsigned, unsigned) { record(c, "dispatch", true); return false; }
bool on_indirect(api::command_list *c, api::indirect_command type, api::resource, std::uint64_t, unsigned, unsigned) {
    record(c, "indirect", type == api::indirect_command::dispatch); return false;
}
void on_submit(api::command_queue *queue, api::command_list *cmd) {
    observe(queue->get_device(), [&](Device &d) { if (d.capturing && d.events.size() < max_events) d.events.push_back(
        "{\"kind\":\"submit\",\"frame\":" + std::to_string(d.frame) + ",\"command_list\":" + quote(hex(reinterpret_cast<Handle>(cmd))) + "}"); });
}
void on_swapchain(api::swapchain *swapchain, bool) {
    observe(swapchain->get_device(), [&](Device &d) {
        auto &buffers = d.backbuffers[swapchain]; buffers.clear();
        for (unsigned i = 0; i < std::min(swapchain->get_back_buffer_count(), 16u); ++i) {
            const auto r = swapchain->get_back_buffer(i);
            const auto desc = swapchain->get_device()->get_resource_desc(r);
            if (!d.ledger.resolve(r.handle)) d.ledger.create(r.handle, desc.texture.width, desc.texture.height, static_cast<unsigned>(desc.texture.format), static_cast<unsigned>(desc.usage));
            buffers.push_back(r.handle);
        }
    });
}
void on_destroy_swapchain(api::swapchain *swapchain, bool) {
    observe(swapchain->get_device(), [&](Device &d) {
        const auto it = d.backbuffers.find(swapchain);
        if (it != d.backbuffers.end()) { for (const auto r : it->second) d.ledger.destroy(r); d.backbuffers.erase(it); }
    });
}
void on_present(api::command_queue *queue, api::swapchain *swapchain, const api::rect *, const api::rect *, unsigned, const api::rect *) {
    observe(queue->get_device(), [&](Device &d) {
        ++d.frame;
        const auto back = queue->get_device()->get_resource_desc(swapchain->get_current_back_buffer());
        d.width = back.texture.width; d.height = back.texture.height;
        DWORD foreground = 0; GetWindowThreadProcessId(GetForegroundWindow(), &foreground);
        const bool key = foreground == GetCurrentProcessId() && (GetAsyncKeyState(VK_F10) & 0x8000);
        const bool request = (key && !d.key_down) || (!d.auto_done && auto_frame && d.frame >= auto_frame);
        d.key_down = key;
        if (d.capturing && --d.remaining == 0) {
            d.capturing = false; write_capture(d);
            d.events.clear(); d.constants.clear(); d.referenced.clear(); d.sampled.clear();
        }
        if (!d.capturing && request) {
            d.auto_done = true; d.capturing = true; d.remaining = capture_frames;
            d.capture_start = d.frame; ++d.serial; d.dropped = 0; d.range_samples = 0;
        }
    });
}

void registration(bool add) {
#define EVENT(name, fn) if (add) reshade::register_event<reshade::addon_event::name>(fn); else reshade::unregister_event<reshade::addon_event::name>(fn)
    EVENT(init_device, on_device); EVENT(destroy_device, on_destroy_device);
    EVENT(init_swapchain, on_swapchain); EVENT(destroy_swapchain, on_destroy_swapchain);
    EVENT(init_resource, on_resource); EVENT(destroy_resource, on_destroy_resource);
    EVENT(init_resource_view, on_view); EVENT(destroy_resource_view, on_destroy_view);
    EVENT(init_pipeline, on_pipeline); EVENT(destroy_pipeline, on_destroy_pipeline);
    EVENT(init_pipeline_layout, on_layout); EVENT(destroy_pipeline_layout, on_destroy_layout);
    EVENT(update_descriptor_tables, on_update); EVENT(copy_descriptor_tables, on_copy);
    EVENT(init_command_list, on_init_command); EVENT(destroy_command_list, on_destroy_command); EVENT(reset_command_list, on_reset);
    EVENT(bind_pipeline, on_bind_pipeline); EVENT(bind_render_targets_and_depth_stencil, on_targets); EVENT(begin_render_pass, on_render_pass);
    EVENT(bind_descriptor_tables, on_tables); EVENT(push_descriptors, on_push);
    EVENT(map_buffer_region, on_map); EVENT(unmap_buffer_region, on_unmap);
    EVENT(draw, on_draw); EVENT(draw_indexed, on_draw_indexed); EVENT(dispatch, on_dispatch); EVENT(draw_or_dispatch_indirect, on_indirect);
    EVENT(execute_command_list, on_submit); EVENT(present, on_present);
#undef EVENT
}
}

extern "C" __declspec(dllexport) const char *NAME = "rtxForge Renderer Diagnostics";
extern "C" __declspec(dllexport) const char *DESCRIPTION = "Independent pass-through D3D12 input diagnostics. SR and FG are not implemented.";
BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        addon_module = module;
        DisableThreadLibraryCalls(module);
        if (!reshade::register_addon(module)) return FALSE;
        registration(true);
    } else if (reason == DLL_PROCESS_DETACH) {
        registration(false); reshade::unregister_addon(module);
    }
    return TRUE;
}
