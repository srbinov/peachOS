// Superellipse ("squircle") maths, ported verbatim from the KDE repo's
// TickRing.qml. Used to lay the digital clock's tick ring between two inset
// squircle frames that match the glass silhouette.

// Signed level-set of a centred squircle: half-extents (hw, hh), corner radius
// r, exponent n. Negative inside, positive outside.
export function squircleLevel(x, y, hw, hh, r, n) {
    const ax = Math.abs(x);
    const ay = Math.abs(y);
    const qx = ax - hw + r;
    const qy = ay - hh + r;
    if (qx <= 0 && qy <= 0)
        return Math.max(qx, qy) - r;
    const mx = Math.max(qx, 0);
    const my = Math.max(qy, 0);
    const arc = Math.pow(Math.pow(mx, n) + Math.pow(my, n), 1 / n);
    return Math.min(Math.max(qx, qy), 0) + arc - r;
}

// Point where the ray from the origin in direction (dx, dy) crosses the
// squircle boundary. Bisection from an AABB bracket.
export function squircleRayHit(dx, dy, hw, hh, r, n) {
    const tX = Math.abs(dx) > 1e-9 ? hw / Math.abs(dx) : Infinity;
    const tY = Math.abs(dy) > 1e-9 ? hh / Math.abs(dy) : Infinity;
    let tHi = Math.min(tX, tY);
    let tLo = 0;
    for (let i = 0; i < 24; i++) {
        const tm = 0.5 * (tLo + tHi);
        if (squircleLevel(tm * dx, tm * dy, hw, hh, r, n) < 0)
            tLo = tm;
        else
            tHi = tm;
    }
    const t = 0.5 * (tLo + tHi);
    return [t * dx, t * dy];
}

// Trace a filled squircle path (centred at cx, cy) into a Cairo context.
export function squirclePath(cr, cx, cy, hw, hh, r, n, steps = 96) {
    r = Math.min(r, hw, hh);
    for (let i = 0; i <= steps; i++) {
        const a = (i / steps) * 2 * Math.PI;
        const dx = Math.cos(a);
        const dy = Math.sin(a);
        const [px, py] = squircleRayHit(dx, dy, hw, hh, r, n);
        if (i === 0)
            cr.moveTo(cx + px, cy + py);
        else
            cr.lineTo(cx + px, cy + py);
    }
    cr.closePath();
}
