using System.Runtime.InteropServices;
using Microsoft.UI.Dispatching;
using Windows.UI;

namespace RtxForge.Windows.Services;

/// <summary>A short-lived, explicit screen pick. Hooks are released on selection, Escape or cancellation.</summary>
static class ScreenColorPicker
{
    delegate nint Hook(int code,nint message,nint data);
    [StructLayout(LayoutKind.Sequential)] struct Point { public int X,Y; }
    [StructLayout(LayoutKind.Sequential)] struct Mouse { public Point Position; public uint Data,Flags,Time; public nuint Extra; }
    [DllImport("user32.dll")] static extern nint SetWindowsHookExW(int kind,Hook hook,nint module,uint thread);
    [DllImport("user32.dll")] static extern bool UnhookWindowsHookEx(nint hook);
    [DllImport("user32.dll")] static extern nint CallNextHookEx(nint hook,int code,nint message,nint data);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern nint GetModuleHandleW(string? name);
    [DllImport("user32.dll")] static extern nint GetDC(nint window);
    [DllImport("user32.dll")] static extern int ReleaseDC(nint window,nint dc);
    [DllImport("user32.dll")] static extern bool GetCursorPos(out Point point);
    [DllImport("gdi32.dll")] static extern uint GetPixel(nint dc,int x,int y);
    static Color? Read(Point point)
    {
        var dc=GetDC(0);if(dc==0)return null;
        try {var rgb=GetPixel(dc,point.X,point.Y);return rgb==uint.MaxValue?null:Color.FromArgb(255,(byte)rgb,(byte)(rgb>>8),(byte)(rgb>>16));}
        finally {ReleaseDC(0,dc);}
    }
    public static async Task<Color?> PickAsync(DispatcherQueue dispatcher,Action<Color> preview,CancellationToken cancel)
    {
        var done=new TaskCompletionSource<Color?>();
        Hook mouse=(code,message,data)=>{
            if(code>=0&&message==0x201){done.TrySetResult(Read(Marshal.PtrToStructure<Mouse>(data).Position));return 1;}
            if(code>=0&&message==0x204){done.TrySetResult(null);return 1;}
            return CallNextHookEx(0,code,message,data);
        };
        Hook keyboard=(code,message,data)=>{
            if(code>=0&&(message==0x100||message==0x104)&&Marshal.ReadInt32(data)==27){done.TrySetResult(null);return 1;}
            return CallNextHookEx(0,code,message,data);
        };
        var mh=SetWindowsHookExW(14,mouse,GetModuleHandleW(null),0);
        var kh=SetWindowsHookExW(13,keyboard,GetModuleHandleW(null),0);
        var timer=dispatcher.CreateTimer();timer.Interval=TimeSpan.FromMilliseconds(100);
        timer.Tick+=(_,_)=>{if(GetCursorPos(out var at)&&Read(at) is { } color)preview(color);};
        try {
            if(mh==0||kh==0)throw new InvalidOperationException("Screen picking is unavailable. Choose a color from the poster or picker.");
            using var registration=cancel.Register(()=>done.TrySetResult(null));timer.Start();return await done.Task;
        }
        finally {timer.Stop();if(mh!=0)UnhookWindowsHookEx(mh);if(kh!=0)UnhookWindowsHookEx(kh);GC.KeepAlive(mouse);GC.KeepAlive(keyboard);}
    }
}
