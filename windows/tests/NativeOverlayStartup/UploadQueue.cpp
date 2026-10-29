#include <windows.h>
#include <d3d12.h>
#include <dxgi1_6.h>
#include <wrl/client.h>
#include <iostream>
#include <stdexcept>

using Microsoft::WRL::ComPtr;
void Need(HRESULT hr) { if (FAILED(hr)) throw std::runtime_error("Direct3D call failed"); }

int main()
{
    ComPtr<ID3D12Fence> blocked;
    try
    {
        ComPtr<ID3D12Device> device;
        Need(D3D12CreateDevice(nullptr, D3D_FEATURE_LEVEL_11_0, IID_PPV_ARGS(&device)));
        D3D12_COMMAND_QUEUE_DESC desc = {};
        desc.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
        ComPtr<ID3D12CommandQueue> game, upload;
        Need(device->CreateCommandQueue(&desc, IID_PPV_ARGS(&game)));
        Need(device->CreateCommandQueue(&desc, IID_PPV_ARGS(&upload)));
        ComPtr<ID3D12Fence> gameDone, uploadDone;
        Need(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&blocked)));
        Need(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&gameDone)));
        Need(device->CreateFence(0, D3D12_FENCE_FLAG_NONE, IID_PPV_ARGS(&uploadDone)));

        // Model a game's render queue waiting for presentation. Do not stall the test's CPU.
        Need(game->Wait(blocked.Get(), 1));
        Need(game->Signal(gameDone.Get(), 1));
        ComPtr<ID3D12CommandAllocator> allocator;
        ComPtr<ID3D12GraphicsCommandList> list;
        Need(device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT, IID_PPV_ARGS(&allocator)));
        Need(device->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT, allocator.Get(), nullptr, IID_PPV_ARGS(&list)));
        Need(list->Close());
        ID3D12CommandList* lists[] = {list.Get()};
        upload->ExecuteCommandLists(1, lists);
        Need(upload->Signal(uploadDone.Get(), 1));
        HANDLE event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
        if (!event) throw std::runtime_error("Could not create fence event");
        Need(uploadDone->SetEventOnCompletion(1, event));
        const auto result = WaitForSingleObject(event, 2000);
        const bool gameStillBlocked = gameDone->GetCompletedValue() == 0;
        Need(blocked->Signal(1));
        if (result != WAIT_OBJECT_0 || !gameStillBlocked)
        { CloseHandle(event); throw std::runtime_error("Upload depends on the blocked game queue"); }
        Need(gameDone->SetEventOnCompletion(1, event));
        const auto resumed = WaitForSingleObject(event, 2000);
        CloseHandle(event);
        if (resumed != WAIT_OBJECT_0) throw std::runtime_error("Game queue did not resume");
        std::cout << "PASS: an independent upload queue completes while the game queue awaits presentation; both queues resume without an infinite CPU wait.\n";
        return 0;
    }
    catch (const std::exception& error)
    {
        if (blocked) blocked->Signal(1);
        std::cerr << error.what() << '\n';
        return 1;
    }
}
