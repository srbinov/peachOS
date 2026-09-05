# peachOS Desktop Widgets

macOS-style liquid-glass desktop widgets for peachOS (GNOME Shell 50).

**Status: Phase 0 (shader spike).** Renders one glass + one solid squircle on
the desktop to prove the ported refraction shader works. No picker, no
persistence yet. See `.claude/plans/fluffy-dreaming-canyon.md` in the repo.

## Attribution

The liquid-glass shader (`shaders/liquidglass.glsl`) is re-implemented from
[`jaxparrow07/liquidglass-kde-widgets`](https://github.com/jaxparrow07/liquidglass-kde-widgets)
(`1-common/components/shaders/liquidglass.frag`), which is itself ported from
[`iyinchao/liquid-glass-studio`](https://github.com/iyinchao/liquid-glass-studio).
Ported from Qt RHI GLSL to Clutter/Cogl GLSL for GNOME Shell. **GPL-3.0.**

The `Clutter.ShaderEffect` wiring follows the patterns in
`blur-my-shell@aunetx` (also GPL-3).

Bundled Apple design-system fonts / icons (added in later phases) are for
personal, non-commercial use only, same footing as peachOS's other
Apple-derived assets. Not affiliated with Apple Inc.
