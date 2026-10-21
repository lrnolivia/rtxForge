namespace RtxForge.Windows.GameMode;

/// <summary>Physical positions match Windows gamepad actions, including Nintendo's labels.</summary>
public sealed record ControllerPrompt(string Label, string Color, string Shape = "text")
{
    public static ControllerPrompt For(string family, string action)
    {
        var face = action switch { "accept" => 0, "back" => 1, "select" => 2, "search" => 3, _ => -1 };
        if (face >= 0)
            return family switch
            {
                "playstation" => new(new[] { "Cross", "Circle", "Square", "Triangle" }[face],
                    new[] { "#72baff", "#ff8187", "#ef9bc9", "#75d9b1" }[face],
                    new[] { "cross", "circle", "square", "triangle" }[face]),
                "nintendo" => new(new[] { "B", "A", "Y", "X" }[face],
                    new[] { "#ffe17c", "#ff8187", "#75d9b1", "#72baff" }[face]),
                "steam" => new(new[] { "A", "B", "X", "Y" }[face], "#e6e8eb"),
                "generic" => new(new[] { "South", "East", "West", "North" }[face], "#e6e8eb", "position" + face),
                _ => new(new[] { "A", "B", "X", "Y" }[face],
                    new[] { "#8cdb80", "#ff8187", "#72baff", "#ffe17c" }[face]),
            };
        return action switch
        {
            "menu" => new(family == "nintendo" ? "+" : "Menu", "#e6e8eb", family == "nintendo" ? "plus" : "menu"),
            "settings" => new(family == "nintendo" ? "−" : "View", "#e6e8eb", family == "nintendo" ? "minus" : "view"),
            "previous" => new(family == "playstation" ? "L1" : family == "nintendo" ? "L" : "LB", "#e6e8eb", "shoulder"),
            "next" => new(family == "playstation" ? "R1" : family == "nintendo" ? "R" : "RB", "#e6e8eb", "shoulder"),
            "move" or "adjust" => new("D-pad", "#e6e8eb", "dpad"),
            _ => new("Menu", "#e6e8eb", "menu"),
        };
    }
}
