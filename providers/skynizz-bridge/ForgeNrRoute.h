// SPDX-License-Identifier: GPL-3.0-only
#pragma once

namespace ForgeNrRoute
{
struct FlagScope
{
    bool& flag;
    bool previous;
    FlagScope(bool& target, bool value) : flag(target), previous(target) { flag = value; }
    ~FlagScope() { flag = previous; }
    FlagScope(const FlagScope&) = delete;
    FlagScope& operator=(const FlagScope&) = delete;
};
// Shared by native passthrough and OptiScaler's internal SR route. RR retains
// the finished-image route until its denoising input contract is validated.
template<class Begin, class Before, class Evaluate, class Restore, class After, class Success, class Finish>
auto Run(bool superResolution, bool rayReconstruction, Begin begin, Before before, Evaluate evaluate,
         Restore restore, After after, Success success, Finish finish)
{
    if (!superResolution && !rayReconstruction)
        return evaluate(); // FG and unrelated NGX features never invoke NR hooks.

    begin();
    struct RestoreInputs
    {
        Restore& callback;
        bool pending = true;
        void Now() { if (pending) { pending = false; callback(); } }
        ~RestoreInputs() { Now(); }
    } inputs { restore };

    const bool prepared = superResolution && before();
    const auto result = evaluate();
    inputs.Now(); // Restore the game's colour before the post hook or any return.
    const bool accepted = success(result);
    if (accepted)
        after(); // The existing pre-SR latch suppresses a second composition pass.
    finish(accepted, prepared);
    return result;
}
}
