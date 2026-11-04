/*
 * Copyright (C) 2026
 * SPDX-License-Identifier: MIT
 *
 * rtxForge live settings interface, version 1, for the RenoDX DLSS5 add-on.
 * Included at the end of addon.cpp by Build-RenoDXCandidate.ps1. It reuses
 * the add-on's own settings table: a host change goes through the same
 * Setting::Commit the add-on's overlay calls, so the value, its ini write and
 * its history reset or feature rebuild are exactly what a slider move does.
 *
 * Only keys with a bound below are reachable, and a value outside its bound is
 * refused rather than clamped. NeuralUplift is left to the toggle key, whose
 * path also resets the failure latches.
 */
#pragma once

#include <cmath>
#include <cstdint>
#include <cstring>

namespace renodx::addons::dlss5::internal::rtxforge_live {

struct Bound {
  const char* key;
  float lo;
  float hi;
  bool integer;
};

// The ranges LoadConfiguration enforces for these keys.
inline constexpr Bound kBounds[] = {
    {"NRIntensity", 0.f, 2.f, false},
    {"NRPreset", 0.f, 3.f, true},
    {"NRStyle", 0.f, 2.f, true},
    {"NRPasses", 1.f, static_cast<float>(kMaxNrPasses), true},
    {"NRResolutionScale", 0.33f, 1.f, false},
    {"NRLocalStructure", 0.f, 2.f, false},
};

inline const Bound* FindBound(const char* key) {
  for (const Bound& bound : kBounds) {
    if (std::strcmp(bound.key, key) == 0) return &bound;
  }
  return nullptr;
}

inline const Setting* FindSetting(const char* key) {
  for (const SettingGroup& group : kSettingSections) {
    for (const Setting* setting : group) {
      if (std::strcmp(setting->key, key) == 0) return setting;
    }
  }
  return nullptr;
}

enum Result : int { kApplied = 0, kUnknownKey = 1, kRefused = 2 };

}  // namespace renodx::addons::dlss5::internal::rtxforge_live

// Returns 1. A host must refuse any other version.
extern "C" __declspec(dllexport) uint32_t __cdecl RenoDXNrApiVersion() { return 1; }

// The live value of a reachable key, and the current configuration generation.
extern "C" __declspec(dllexport) bool __cdecl RenoDXNrGetV1(
    const char* key, float* value, uint64_t* generation) {
  namespace live = renodx::addons::dlss5::internal::rtxforge_live;
  if (key == nullptr || value == nullptr) return false;
  if (live::FindBound(key) == nullptr) return false;
  const auto* setting = live::FindSetting(key);
  if (setting == nullptr) return false;
  *value = setting->Get();
  if (generation != nullptr) {
    *generation = renodx::addons::dlss5::internal::configuration_generation.load();
  }
  return true;
}

// Commits a change. *applied is the value read back after the commit, and
// *generation the configuration generation a rebuild must reach.
extern "C" __declspec(dllexport) int __cdecl RenoDXNrSetV1(
    const char* key, float value, float* applied, uint64_t* generation) {
  namespace live = renodx::addons::dlss5::internal::rtxforge_live;
  if (key == nullptr || applied == nullptr) return live::kRefused;
  const auto* bound = live::FindBound(key);
  const auto* setting = bound != nullptr ? live::FindSetting(key) : nullptr;
  if (setting == nullptr) return live::kUnknownKey;
  if (!std::isfinite(value) || value < bound->lo || value > bound->hi
      || (bound->integer && std::floor(value) != value)) {
    return live::kRefused;
  }
  setting->Commit(value);
  *applied = setting->Get();
  if (generation != nullptr) {
    *generation = renodx::addons::dlss5::internal::configuration_generation.load();
  }
  return live::kApplied;
}

// The configuration generation every live NR feature has been rebuilt for:
// the oldest one, or 0 while no feature exists. A rebuild has applied once
// this reaches the generation RenoDXNrSetV1 returned.
extern "C" __declspec(dllexport) uint64_t __cdecl RenoDXNrAppliedGenerationV1() {
  using namespace renodx::addons::dlss5::internal;
  RuntimeLock lock(runtime_mutex);
  uint64_t oldest = 0;
  bool any = false;
  for (auto& [_, feature] : features) {
    const uint64_t built = feature.slots[0].configuration_generation;
    if (!any || built < oldest) oldest = built;
    any = true;
  }
  return any ? oldest : 0;
}
