#pragma once
#include <mutex>
#include <unordered_map>
namespace fgvk {
struct NgxFeature { unsigned id{}; int flags{-1}; };
class FeatureRegistry {
    std::mutex mutex;
    std::unordered_map<const void*, NgxFeature> features;
public:
    void Created(const void* handle, unsigned id, int flags) {
        if (!handle) return;
        std::lock_guard<std::mutex> lock(mutex);
        features[handle] = {id, flags};
    }
    void Released(const void* handle) {
        std::lock_guard<std::mutex> lock(mutex);
        features.erase(handle);
    }
    NgxFeature Find(const void* handle) {
        std::lock_guard<std::mutex> lock(mutex);
        auto feature = features.find(handle);
        return feature == features.end() ? NgxFeature{} : feature->second;
    }
};
}
