namespace RtxForge.Windows.Models;

public sealed record AppStorageCategory(string Title, string Detail, long Bytes, bool Cache);

public sealed record AppStorage(long Bytes, IReadOnlyList<AppStorageCategory> Categories, string? Warning)
{
    public long DownloadBytes => Categories.Where(c => c.Cache).Sum(c => c.Bytes);
    public static string Format(long bytes)
    {
        double value = bytes;
        string[] units = ["B", "KiB", "MiB", "GiB", "TiB"];
        var index = 0;
        while (value >= 1024 && index < units.Length - 1) { value /= 1024; index++; }
        return index == 0 ? $"{value:0} B" : $"{value:0.0} {units[index]}";
    }
}
