// SPDX-License-Identifier: GPL-3.0-only
#include "ForgeNrRoute.h"
#include <stdexcept>
#include <string>
#include <iostream>

void need(bool condition) { if (!condition) throw std::runtime_error("NR routing regression"); }

int main()
{
    int cases = 0;
    for (bool native : {false, true})
    for (int feature : {0, 1, 2, 3}) // SR, RR, FG, unrelated
    for (int mode : {0, 1, 2, 3, 4, 5}) // off, post, pre, refusal, upscale failure, exception
    {
        int models = 0, begins = 0, restores = 0, ends = 0, evaluations = 0;
        bool swapped = false, preRan = true; // A failed prior frame must not leak its latch.
        const bool eligible = feature < 2, enabled = mode != 0;
        const bool wantsBefore = mode >= 2;
        std::string order;
        try
        {
            const auto result = ForgeNrRoute::Run(feature == 0, feature == 1,
                [&] { ++begins; preRan = false; order += 'b'; },
                [&] {
                    if (!enabled || !wantsBefore || mode == 3) return false;
                    ++models; swapped = true; preRan = true; order += 'p'; return true;
                },
                [&] {
                    ++evaluations; order += native ? 'n' : 'i';
                    if (mode == 5) throw std::runtime_error("upscaler exception");
                    return mode == 4 ? -1 : 1;
                },
                [&] { ++restores; swapped = false; order += 'r'; },
                [&] {
                    need(!swapped); order += 'a';
                    if (!preRan && enabled) ++models;
                    preRan = false;
                },
                [](int result) { return result == 1; },
                [&](bool accepted, bool prepared) {
                    ++ends; need(accepted == (mode != 4));
                    need(prepared == (feature == 0 && enabled && wantsBefore && mode != 3));
                });
            need(result == (mode == 4 ? -1 : 1));
        }
        catch (const std::runtime_error& error)
        {
            if (std::string(error.what()) != "upscaler exception") throw;
            need(mode == 5 && ends == 0);
        }
        need(evaluations == 1 && !swapped);
        need(begins == int(eligible) && restores == int(eligible));
        need(models <= 1);
        if (!eligible || !enabled) need(models == 0);
        if (feature == 1) need(order.find('p') == std::string::npos);
        if (eligible && mode == 3) need(models == 1); // Refused pre hook falls back once.
        ++cases;
    }
    // Even a pre hook that throws after replacing the colour restores it.
    bool restored = false;
    try
    {
        ForgeNrRoute::Run(true, false, [] {}, []() -> bool { throw std::runtime_error("pre failure"); },
            [] { return 1; }, [&] { restored = true; }, [] { need(false); },
            [](int) { return true; }, [](bool, bool) { need(false); });
    }
    catch (const std::runtime_error&) { need(restored); }
    bool preDispatch = false;
    try
    {
        const ForgeNrRoute::FlagScope scope(preDispatch, true);
        need(preDispatch);
        throw std::runtime_error("dispatch exception");
    }
    catch (const std::runtime_error&) { need(!preDispatch); }
    ForgeNrRoute::Observations observation;
    observation.Begin(true, true);
    observation.ModelEvaluated(false, 1920, 1080, false);
    need(observation.Published().actual == 0); // No partial publication.
    observation.Finish(true, true, 1000);
    auto actual = observation.Published();
    need(actual.actual == 3 && actual.reason == 1 && actual.requestedBefore && actual.modelWidth == 1920 && !actual.reduced);
    observation.Begin(true, false);
    observation.ModelEvaluated(true, 1280, 720, true);
    need(observation.Published().actual == 3 && observation.Published().tick == 1000);
    observation.Finish(true, true, 1100);
    actual = observation.Published();
    need(actual.actual == 2 && actual.reason == 0 && actual.reduced && actual.modelWidth == 1280);
    observation.Begin(true, false); observation.Finish(true, true, 1200);
    actual = observation.Published();
    need(actual.actual == 4 && actual.reason == 4 && actual.modelWidth == 0);
    observation.Begin(true, false); observation.ModelEvaluated(true, 1280, 720, true);
    observation.Finish(false, true, 1300); actual = observation.Published();
    need(actual.actual == 4 && actual.reason == 3 && actual.modelWidth == 0 && !actual.reduced);
    observation.Begin(false, false); observation.Finish(true, false, 1400);
    actual = observation.Published(); need(actual.actual == 1 && actual.reason == 0 && actual.modelWidth == 0);
    observation.Begin(true, false); observation.ModelEvaluated(false, 1920, 1080, false);
    observation.Finish(true, true, 1500); actual = observation.Published();
    need(actual.actual == 3 && actual.reason == 2 && actual.modelWidth == 1920);
    std::cout << "PASS: " << cases + 2 << " native/internal SR, RR, FG, off, fallback and restoration cases\n";
    std::cout << "PASS: completed-only observations, actual model sizes, RR/pre fallback, off and failed upscale\n";
}
