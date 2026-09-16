# Visual controls — implemented in 0.5.7

The library header and game details each expose independent NR Strength and Sharpening sliders (Off, Light, Medium, Strong), plus an MFG dropdown (Off, 2× through 6×).

NR intensity / skin: 1.00, 1.50, 2.00. Sharpening: 0.25, 0.375, 0.50. Both initially Strong. Other NR model parameters stay fixed. Off disables the selected effect without removing its files. Requested MFG ratios use the provider's native-game override and preserve native FG routing.

Global changes turn Reset All Settings into Apply Settings; returning every control to its saved default restores the Reset label. Apply updates eligible managed INIs and saves global defaults. Per-game Apply writes only that INI and never changes global preferences. All writes retain prior INI backups and refuse running games. Mixed library profiles remain intact.

No live image-quality simulation or performance guarantee is implied. HQFont stays disabled per the upstream Vulkan workaround. Runtime stability remains user-tested.
