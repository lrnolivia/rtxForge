/*
 * Copyright (C) 2026
 * SPDX-License-Identifier: MIT
 *
 * RenoDX shared utilities the DLSS5 add-on source expects but public RenoDX
 * does not have. The add-on was imported from a RenoDX base (3a6cfc6) that is
 * not published; these five definitions are rebuilt from how the add-on uses
 * them. Included before dlssnr.hpp by Build-RenoDXCandidate.ps1.
 *
 * NativeIdentity compares COM identity (IUnknown). If the unpublished base
 * also unwrapped ReShade proxies, a mismatch makes the add-on decline the
 * frame as "a different device": NR stays off rather than misbehaving.
 */
#pragma once

#include <windows.h>
#include <unknwn.h>

#include <atomic>
#include <cstdint>
#include <mutex>

#include <detours.h>

// Before anything that includes reshade.hpp: ReShade defines its Dear ImGui
// wrappers only when imgui.h is already included, as dlssnr.hpp arranges.
#include <deps/imgui/imgui.h>

#include "../../utils/directx.hpp"
#include "../../utils/vtable.hpp"

namespace renodx::utils::directx {

// The object's COM identity, for comparison only; never dereferenced.
template <typename T>
inline IUnknown* NativeIdentity(T* object) {
  if (object == nullptr) return nullptr;
  IUnknown* identity = nullptr;
  if (FAILED(reinterpret_cast<IUnknown*>(object)->QueryInterface(
          __uuidof(IUnknown), reinterpret_cast<void**>(&identity)))
      || identity == nullptr) {
    return reinterpret_cast<IUnknown*>(object);
  }
  identity->Release();
  return identity;
}

template <typename A, typename B>
inline bool SameNativeObject(A* a, B* b) {
  return a != nullptr && b != nullptr && NativeIdentity(a) == NativeIdentity(b);
}

}  // namespace renodx::utils::directx

namespace renodx::utils::vtable {

// Detours allows one pending transaction per process. Callers hold this
// mutex around a transaction; transaction_contended counts the times another
// thread's transaction was pending anyway.
inline std::mutex& TransactionMutex() {
  static std::mutex mutex;
  return mutex;
}

inline std::atomic_uint64_t transaction_contended{0};

inline bool BeginTransaction() {
  if (DetourTransactionBegin() == NO_ERROR) return true;
  transaction_contended.fetch_add(1, std::memory_order_relaxed);
  return false;
}

}  // namespace renodx::utils::vtable
