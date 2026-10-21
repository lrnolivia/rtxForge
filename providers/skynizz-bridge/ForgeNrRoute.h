// SPDX-License-Identifier: GPL-3.0-only
#pragma once

namespace ForgeNrRoute
{
struct Observation
{
    unsigned int actual = 0, reason = 0;
    unsigned int modelWidth = 0, modelHeight = 0, tick = 0;
    bool reduced = false, requestedBefore = false;
};

// Publish only completed upscales. A concurrent FG snapshot keeps the previous
// completed observation while the next model evaluation is in progress.
class Observations
{
    Observation pending, completed;
    bool rayReconstruction = false;
public:
    void Begin(bool requestedBefore, bool rr)
    {
        pending = {}; pending.requestedBefore = requestedBefore; rayReconstruction = rr;
    }
    void ModelEvaluated(bool before, unsigned int width, unsigned int height, bool reduced)
    {
        pending.actual = before ? 2 : 3;
        pending.modelWidth = width; pending.modelHeight = height;
        pending.reduced = before && reduced;
    }
    void Finish(bool success, bool enabled, unsigned int tick)
    {
        if (!success || !enabled)
        {
            pending.actual = success ? 1 : 4; pending.reason = success ? 0 : 3;
            pending.modelWidth = pending.modelHeight = 0; pending.reduced = false;
        }
        else if (pending.actual == 0) { pending.actual = 4; pending.reason = 4; }
        else if (pending.requestedBefore && pending.actual == 3) pending.reason = rayReconstruction ? 1 : 2;
        pending.tick = tick; completed = pending;
    }
    Observation Published() const { return completed; }
};

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
