"""
Medieval village asset generator (Blender / bpy, runs headless).

Builds every asset procedurally, exports one FBX per asset (meters, Z up, origin at the base),
writes manifest.json (asset metadata: chimney tops, doors, windows) and layout.json (where every
asset goes in the village), and can render preview images with Cycles.

  python3 build_village_assets.py --out <dir> [--preview]

Coordinate convention (Blender): +Z up, house fronts face -Y, units = meters.
"""

import argparse
import json
import math
import os
import random
import sys

import bpy
import bmesh
from mathutils import Vector

# ----------------------------------------------------------------------------
# Materials (names become Unreal material slots; colors only matter for previews)
# ----------------------------------------------------------------------------
MAT_COLORS = {
    "Stone": (0.42, 0.40, 0.37), "StoneDark": (0.28, 0.27, 0.25), "Plaster": (0.80, 0.74, 0.62),
    "PlasterB": (0.84, 0.80, 0.70), "Timber": (0.22, 0.13, 0.07), "Planks": (0.38, 0.25, 0.14),
    "RoofShingle": (0.25, 0.22, 0.20), "RoofTile": (0.48, 0.16, 0.10), "Thatch": (0.62, 0.50, 0.26),
    "RoofSlate": (0.20, 0.21, 0.24), "Door": (0.30, 0.17, 0.08), "Glass": (0.10, 0.16, 0.22),
    "Brick": (0.45, 0.20, 0.12), "Grass": (0.20, 0.32, 0.10), "Dirt": (0.36, 0.27, 0.17),
    "Cobble": (0.40, 0.38, 0.35), "Water": (0.05, 0.12, 0.16), "Bark": (0.20, 0.14, 0.09),
    "Leaves": (0.13, 0.30, 0.07), "LeavesDark": (0.07, 0.20, 0.06), "Rock": (0.38, 0.37, 0.35),
    "ClothRed": (0.55, 0.10, 0.08), "ClothBlue": (0.12, 0.20, 0.45), "ClothCream": (0.82, 0.78, 0.66),
    "Hay": (0.78, 0.66, 0.32), "Metal": (0.30, 0.30, 0.32), "Snow": (0.92, 0.93, 0.95),
}
_mats = {}


def mat(name):
    if name not in _mats:
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        c = MAT_COLORS.get(name, (0.5, 0.5, 0.5))
        m.diffuse_color = (c[0], c[1], c[2], 1.0)
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
            bsdf.inputs["Roughness"].default_value = 0.1 if name in ("Glass", "Water") else 0.85
        _mats[name] = m
    return _mats[name]


# ----------------------------------------------------------------------------
# Mesh primitives (all built with bmesh, no bpy.ops, so it is fast and deterministic)
# ----------------------------------------------------------------------------
class Part(list):
    """A list of objects that will be joined into one exported asset."""


def _obj_from_bm(bm, name, material):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(mat(material))
    return ob


def box(parts, center, size, material, yaw=0.0, roll=0.0, pitch=0.0, name="box"):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if roll or pitch or yaw:
        from mathutils import Euler
        bmesh.ops.rotate(bm, verts=bm.verts, cent=Vector((0, 0, 0)),
                         matrix=Euler((math.radians(roll), math.radians(pitch), math.radians(yaw)), "XYZ").to_matrix())
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    ob = _obj_from_bm(bm, name, material)
    parts.append(ob)
    return ob


def cylinder(parts, center, radius, depth, material, segments=12, r2=None, rot=(0, 0, 0), name="cyl"):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments, radius1=radius,
                          radius2=radius if r2 is None else r2, depth=depth)
    if any(rot):
        from mathutils import Euler
        bmesh.ops.rotate(bm, verts=bm.verts, cent=Vector((0, 0, 0)),
                         matrix=Euler(tuple(math.radians(a) for a in rot), "XYZ").to_matrix())
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    ob = _obj_from_bm(bm, name, material)
    parts.append(ob)
    return ob


def blob(parts, center, radius, material, jitter=0.25, subdiv=2, squash=1.0, name="blob", rng=None):
    rng = rng or random
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=radius)
    for v in bm.verts:
        n = v.co.normalized()
        v.co += n * radius * rng.uniform(-jitter, jitter)
        v.co.z *= squash
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    ob = _obj_from_bm(bm, name, material)
    parts.append(ob)
    return ob


def prism(parts, profile_yz, x0, x1, material, name="prism"):
    """Extrude a 2D polygon given in (y, z) along X from x0 to x1."""
    bm = bmesh.new()
    a = [bm.verts.new((x0, y, z)) for (y, z) in profile_yz]
    b = [bm.verts.new((x1, y, z)) for (y, z) in profile_yz]
    n = len(profile_yz)
    bm.faces.new(list(reversed(a)))
    bm.faces.new(b)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _obj_from_bm(bm, name, material)
    parts.append(ob)
    return ob


def pyramid(parts, center, half, height, material, name="spire"):
    bm = bmesh.new()
    cx, cy, cz = center
    base = [bm.verts.new((cx + sx * half, cy + sy * half, cz)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    top = bm.verts.new((cx, cy, cz + height))
    bm.faces.new(list(reversed(base)))
    for i in range(4):
        bm.faces.new((base[i], base[(i + 1) % 4], top))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _obj_from_bm(bm, name, material)
    parts.append(ob)
    return ob


# ----------------------------------------------------------------------------
# Walls with openings (windows / doors), timber framing, roofs
# ----------------------------------------------------------------------------
def wall(parts, glass, p0, direction, normal, length, z0, height, thick, material, openings, frame_mat="Timber",
         shutters=True, rng=None):
    """Wall from p0 along `direction`; outer face toward `normal`.
    openings: list of (u_center, width, z_bottom, z_top, kind) with kind 'window' | 'door' | 'hole'."""
    rng = rng or random
    d = Vector(direction).normalized()
    n = Vector(normal).normalized()
    yaw = math.degrees(math.atan2(d.y, d.x))
    p0 = Vector(p0)

    def piece(u0, u1, zb, zt, m=material, inset=0.0, th=thick):
        if u1 - u0 < 0.01 or zt - zb < 0.01:
            return
        c = p0 + d * ((u0 + u1) / 2) - n * (th / 2 + inset)
        box(parts, (c.x, c.y, (zb + zt) / 2), (u1 - u0, th, zt - zb), m, yaw=yaw)

    ops = sorted(openings, key=lambda o: o[0])
    u = 0.0
    for (uc, w, zb, zt, kind) in ops:
        a, b = uc - w / 2, uc + w / 2
        piece(u, a, z0, z0 + height)
        piece(a, b, z0, zb)                      # below the opening
        piece(a, b, zt, z0 + height)             # above the opening
        # frame (protrudes 4 cm)
        f = 0.09
        for (fu0, fu1, fzb, fzt) in ((a - f, a, zb, zt), (b, b + f, zb, zt), (a - f, b + f, zt, zt + f),
                                     (a - f, b + f, zb - (f if kind != "door" else 0), zb)):
            c = p0 + d * ((fu0 + fu1) / 2) + n * 0.02
            box(parts, (c.x, c.y, (fzb + fzt) / 2), (fu1 - fu0, thick + 0.04, max(fzt - fzb, 0.01)), frame_mat, yaw=yaw)
        if kind == "window":
            c = p0 + d * uc - n * (thick * 0.5)
            box(glass, (c.x, c.y, (zb + zt) / 2), (w, 0.03, zt - zb), "Glass", yaw=yaw, name="glass")
            box(parts, (c.x, c.y, (zb + zt) / 2), (0.05, 0.05, zt - zb), frame_mat, yaw=yaw)   # mullion
            if shutters:
                for s in (-1, 1):
                    sc = p0 + d * (uc + s * (w / 2 + 0.05 + w / 4)) + n * 0.04
                    box(parts, (sc.x, sc.y, (zb + zt) / 2), (w / 2, 0.04, (zt - zb) * 0.98),
                        rng.choice(["Door", "Timber", "Planks"]), yaw=yaw)
        elif kind == "door":
            c = p0 + d * uc - n * (thick * 0.35)
            box(parts, (c.x, c.y, (zb + zt) / 2), (w, 0.06, zt - zb), "Door", yaw=yaw)
            # step
            sc = p0 + d * uc + n * 0.3
            box(parts, (sc.x, sc.y, z0 + 0.08), (w + 0.4, 0.6, 0.16), "Stone", yaw=yaw)
        u = b
    piece(u, length, z0, z0 + height)


def timber_frame(parts, p0, direction, normal, length, z0, height, openings, rng):
    """Half-timbering on the outer face: posts, rails and diagonal braces between openings."""
    d = Vector(direction).normalized()
    n = Vector(normal).normalized()
    yaw = math.degrees(math.atan2(d.y, d.x))
    p0 = Vector(p0)
    t = 0.14

    def beam_u(u, zb, zt):
        c = p0 + d * u + n * 0.03
        box(parts, (c.x, c.y, (zb + zt) / 2), (t, 0.06, zt - zb), "Timber", yaw=yaw)

    for zr in (z0 + t / 2, z0 + height - t / 2):
        c = p0 + d * (length / 2) + n * 0.03
        box(parts, (c.x, c.y, zr), (length, 0.06, t), "Timber", yaw=yaw)
    edges = [0.07, length - 0.07]
    for (uc, w, zb, zt, kind) in openings:
        edges += [uc - w / 2 - 0.12, uc + w / 2 + 0.12]
    edges = sorted(set(round(e, 3) for e in edges if 0 <= e <= length))
    for e in edges:
        beam_u(e, z0, z0 + height)
    # braces in open spans
    blocked = [(uc - w / 2 - 0.15, uc + w / 2 + 0.15) for (uc, w, zb, zt, kind) in openings]
    for a, b in zip(edges[:-1], edges[1:]):
        if b - a < 0.8 or any(not (b <= x0 or a >= x1) for x0, x1 in blocked):
            continue
        L = math.hypot(b - a, height - 2 * t)
        ang = math.degrees(math.atan2(height - 2 * t, b - a))
        sgn = 1 if rng.random() < 0.5 else -1
        c = p0 + d * ((a + b) / 2) + n * 0.03
        box(parts, (c.x, c.y, z0 + height / 2), (L, 0.06, t), "Timber", yaw=yaw, roll=0, pitch=0,
            name="brace").rotation_euler = (0, 0, 0)
        ob = parts[-1]
        # rotate the brace in the wall plane around its center
        import mathutils
        mw = mathutils.Matrix.Translation(Vector((c.x, c.y, z0 + height / 2))) @ \
            mathutils.Matrix.Rotation(math.radians(yaw), 4, "Z") @ \
            mathutils.Matrix.Rotation(math.radians(-ang * sgn), 4, "Y") @ \
            mathutils.Matrix.Rotation(math.radians(-yaw), 4, "Z") @ \
            mathutils.Matrix.Translation(-Vector((c.x, c.y, z0 + height / 2)))
        ob.data.transform(mw)


def gable_roof(parts, w, d, z_eave, pitch_deg, roof_mat, wall_mat, overhang=0.45, thick=0.22):
    """Ridge along X. Returns ridge height."""
    hd = d / 2
    rise = hd * math.tan(math.radians(pitch_deg))
    # attic block = both gable ends
    prism(parts, [(-hd, z_eave), (hd, z_eave), (0, z_eave + rise)], -w / 2, w / 2, wall_mat, "attic")
    a = hd + overhang
    drop = overhang * math.tan(math.radians(pitch_deg))
    t = thick / math.cos(math.radians(pitch_deg))
    prof = [(-a, z_eave - drop), (0, z_eave + rise), (a, z_eave - drop),
            (a, z_eave - drop - t), (0, z_eave + rise - t), (-a, z_eave - drop - t)]
    prism(parts, list(reversed(prof)), -w / 2 - overhang, w / 2 + overhang, roof_mat, "roof")
    # ridge cap
    box(parts, (0, 0, z_eave + rise + 0.05), (w + 2 * overhang + 0.05, 0.3, 0.16), roof_mat)
    return z_eave + rise


# ----------------------------------------------------------------------------
# Buildings
# ----------------------------------------------------------------------------
def house(name, w, d, floors=1, floor_h=2.8, ground="Stone", upper="Plaster", roof="RoofShingle",
          pitch=50, jetty=0.0, chimney=True, timber=True, door_u=None, seed=1):
    rng = random.Random(seed)
    parts, glass = Part(), Part()
    T = 0.35
    meta = {"size": [w, d], "floors": floors, "windows": [], "doors": []}
    box(parts, (0, 0, 0.12), (w + 0.4, d + 0.4, 0.3), "StoneDark")       # plinth
    z = 0.25
    for f in range(floors):
        fw, fd = (w, d) if f == 0 else (w, d + 2 * jetty)
        wm = ground if f == 0 else upper
        hw, hd = fw / 2, fd / 2
        n_win = max(1, int(fw / 2.6))
        us = [fw * (i + 0.5) / n_win for i in range(n_win)]
        front_ops = []
        if f == 0:
            du = door_u if door_u is not None else fw / 2
            front_ops.append((du, 1.05, z, z + 2.1, "door"))
            meta["doors"].append([-hw + du, -hd, z])
            us = [u for u in us if abs(u - du) > 1.1]
        for u in us:
            front_ops.append((u, 0.85, z + 0.9, z + 2.05, "window"))
            meta["windows"].append([-hw + u, -hd, z + 1.45])
        back_ops = [(u, 0.85, z + 0.9, z + 2.05, "window") for u in us[:max(1, len(us) - 1)]]
        side_ops = [(fd / 2, 0.7, z + 1.0, z + 2.0, "window")] if fd > 4 else []
        walls = [  # (p0, dir, normal, length, openings)
            ((-hw, -hd + T, 0), (1, 0, 0), (0, -1, 0), fw, front_ops),
            ((hw, hd - T, 0), (-1, 0, 0), (0, 1, 0), fw, back_ops),
            ((hw - T, -hd, 0), (0, 1, 0), (1, 0, 0), fd, side_ops),
            ((-hw + T, hd, 0), (0, -1, 0), (-1, 0, 0), fd, side_ops),
        ]
        for (p0, dr, nm, L, ops) in walls:
            # wall p0 is on the inner face line; shift so the outer face sits on the footprint edge
            p = Vector(p0) + Vector(nm) * T
            wall(parts, glass, p, dr, nm, L, z, floor_h, T, wm, ops, rng=rng)
            if timber and wm in ("Plaster", "PlasterB"):
                timber_frame(parts, p, dr, nm, L, z, floor_h, ops, rng)
        if f > 0 and jetty > 0:
            for i in range(int(w / 0.9) + 1):   # joist ends under the overhang
                x = -w / 2 + 0.3 + i * 0.9
                for s in (-1, 1):
                    box(parts, (x, s * (d / 2 + jetty / 2), z - 0.1), (0.16, jetty + 0.2, 0.2), "Timber")
        box(parts, (0, 0, z + floor_h - 0.05), (fw - 2 * T, fd - 2 * T, 0.1), "Planks")    # ceiling
        z += floor_h
    top_d = d + 2 * jetty if floors > 1 else d
    ridge = gable_roof(parts, w, top_d, z, pitch, roof, upper if floors > 1 else ground,
                       thick=0.45 if roof == "Thatch" else 0.22)
    if chimney:
        cx, cy = w * 0.28, top_d * 0.12
        ch_top = ridge + 0.9
        box(parts, (cx, cy, (z + ch_top) / 2), (0.7, 0.7, ch_top - z), "Brick" if rng.random() < 0.5 else "Stone")
        box(parts, (cx, cy, ch_top + 0.06), (0.85, 0.85, 0.12), "StoneDark")
        meta["chimney_top"] = [cx, cy, ch_top + 0.15]
    meta["ridge"] = ridge
    meta["height"] = ridge
    return parts, glass, meta


def church(name="Church"):
    rng = random.Random(7)
    parts, glass = Part(), Part()
    w, d, H = 9.0, 20.0, 7.5      # nave: 9 m wide (x), 20 m long (y)
    T = 0.6
    meta = {"windows": [], "doors": []}
    box(parts, (0, 0, 0.2), (w + 0.6, d + 0.6, 0.4), "StoneDark")
    z = 0.4
    hw, hd = w / 2, d / 2
    side_ops = [(u, 1.1, z + 2.2, z + 5.6, "window") for u in (3.0, 7.0, 11.0, 15.0)]
    for (p0, dr, nm, L, ops) in (
            ((-hw, -hd, 0), (1, 0, 0), (0, -1, 0), w, [(w / 2, 1.8, z, z + 3.2, "door")]),
            ((hw, hd, 0), (-1, 0, 0), (0, 1, 0), w, [(w / 2, 2.0, z + 2.0, z + 6.0, "window")]),
            ((hw, -hd, 0), (0, 1, 0), (1, 0, 0), d, side_ops),
            ((-hw, hd, 0), (0, -1, 0), (-1, 0, 0), d, side_ops)):
        wall(parts, glass, p0, dr, nm, L, z, H, T, "Stone", ops, frame_mat="StoneDark", shutters=False, rng=rng)
    for s in (-1, 1):                         # buttresses
        for u in (1.0, 5.0, 9.0, 13.0, 17.0):
            box(parts, (s * (hw + 0.35), -hd + u, z + 2.5), (0.7, 0.8, 5.0), "Stone")
    meta["doors"].append([0, -hd, z])
    gable_roof(parts, d, w, z + H, 52, "RoofSlate", "Stone", overhang=0.5)
    # gable_roof builds the ridge along X; rotate the roof parts so the ridge runs along Y
    for ob in parts[-3:]:
        import mathutils
        ob.data.transform(mathutils.Matrix.Rotation(math.radians(90), 4, "Z"))
    # bell tower in front of the nave
    tw, th = 4.6, 19.0
    ty = -hd - tw / 2 + 0.3
    tower_ops = [(tw / 2, 1.4, z, z + 2.8, "door")]
    for (p0, dr, nm, L, ops) in (
            ((-tw / 2, ty - tw / 2, 0), (1, 0, 0), (0, -1, 0), tw, tower_ops),
            ((tw / 2, ty + tw / 2, 0), (-1, 0, 0), (0, 1, 0), tw, []),
            ((tw / 2, ty - tw / 2, 0), (0, 1, 0), (1, 0, 0), tw, []),
            ((-tw / 2, ty + tw / 2, 0), (0, -1, 0), (-1, 0, 0), tw, [])):
        wall(parts, glass, p0, dr, nm, L, z, th, 0.7, "Stone", ops, frame_mat="StoneDark", shutters=False, rng=rng)
    # belfry openings (dark louvres) and a clock-band
    for k, (nx, ny) in enumerate(((0, -1), (0, 1), (1, 0), (-1, 0))):
        c = Vector((0, ty, 0)) + Vector((nx, ny, 0)) * (tw / 2 + 0.02)
        yaw = 90 if nx else 0
        box(parts, (c.x, c.y, z + th - 2.8), (1.2 if not nx else 0.08, 0.08 if not nx else 1.2, 2.2), "Timber")
        box(parts, (c.x, c.y, z + th - 6.0), (1.6 if not nx else 0.1, 0.1 if not nx else 1.6, 1.6), "StoneDark")
    box(parts, (0, ty, z + th + 0.2), (tw + 0.5, tw + 0.5, 0.4), "StoneDark")
    pyramid(parts, (0, ty, z + th + 0.4), tw / 2 + 0.2, 11.0, "RoofSlate")
    cylinder(parts, (0, ty, z + th + 11.9), 0.06, 1.8, "Metal")
    box(parts, (0, ty, z + th + 12.4), (0.9, 0.08, 0.08), "Metal")
    meta["height"] = z + th + 12.8
    meta["tower"] = [0, ty, z + th + 11]
    return parts, glass, meta


# ----------------------------------------------------------------------------
# Nature and props
# ----------------------------------------------------------------------------
def tree_oak(seed):
    rng = random.Random(seed)
    p = Part()
    h = rng.uniform(4.0, 5.5)
    cylinder(p, (0, 0, h / 2), rng.uniform(0.32, 0.42), h, "Bark", segments=10, r2=0.22)
    for i in range(3):
        a = rng.uniform(0, 360)
        L = rng.uniform(1.6, 2.4)
        cylinder(p, (math.cos(math.radians(a)) * L * 0.45, math.sin(math.radians(a)) * L * 0.45, h * 0.85),
                 0.12, L, "Bark", segments=6, rot=(0, 60, a))
    for i in range(7):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0.6, 2.2)
        blob(p, (math.cos(a) * r, math.sin(a) * r, h + rng.uniform(0.3, 2.6)), rng.uniform(1.4, 2.3),
             rng.choice(["Leaves", "LeavesDark"]), rng=rng)
    return p, {"height": h + 4.5}


def tree_pine(seed):
    rng = random.Random(seed)
    p = Part()
    h = rng.uniform(9, 14)
    cylinder(p, (0, 0, h * 0.35), 0.28, h * 0.7, "Bark", segments=8, r2=0.12)
    layers = 6
    for i in range(layers):
        t = i / (layers - 1)
        r = 2.6 * (1 - t) + 0.5
        cylinder(p, (0, 0, h * 0.28 + t * h * 0.62), r, 2.4, "LeavesDark", segments=10, r2=0.05)
    return p, {"height": h + 1.0}


def bush(seed):
    rng = random.Random(seed)
    p = Part()
    for i in range(4):
        blob(p, (rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), 0.5), rng.uniform(0.5, 0.9),
             rng.choice(["Leaves", "LeavesDark"]), squash=0.8, rng=rng)
    return p, {}


def rock(seed):
    rng = random.Random(seed)
    p = Part()
    blob(p, (0, 0, 0.4), rng.uniform(0.6, 1.2), "Rock", jitter=0.35, subdiv=1, squash=0.6, rng=rng)
    return p, {}


def well():
    p, water = Part(), Part()
    for i in range(14):
        a = 360.0 * i / 14
        box(p, (1.0 * math.cos(math.radians(a)), 1.0 * math.sin(math.radians(a)), 0.45), (0.5, 0.35, 0.9), "Stone",
            yaw=a + 90)
    cylinder(water, (0, 0, 0.75), 0.85, 0.04, "Water", segments=16)
    for s in (-1, 1):
        box(p, (s * 1.0, 0, 1.6), (0.18, 0.18, 2.6), "Timber")
    box(p, (0, 0, 2.85), (2.4, 0.15, 0.15), "Timber")
    prism(p, [(-1.0, 2.8), (1.0, 2.8), (0, 3.6)], -1.4, 1.4, "RoofShingle")
    cylinder(p, (0, 0, 2.2), 0.1, 1.8, "Timber", rot=(0, 90, 0))
    return p, water, {}


def stall(seed, cloth):
    rng = random.Random(seed)
    p = Part()
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(p, (sx * 1.4, sy * 0.8, 1.2 + (0.25 if sy < 0 else 0)), (0.12, 0.12, 2.4 + (0.5 if sy < 0 else 0)),
                "Timber")
    box(p, (0, 0, 0.85), (2.8, 1.5, 0.08), "Planks")
    box(p, (0, 0, 0.45), (2.6, 1.3, 0.8), "Planks")
    box(p, (0, -0.1, 2.6), (3.2, 2.0, 0.05), cloth, roll=-12)
    for i in range(5):  # goods
        box(p, (rng.uniform(-1.1, 1.1), rng.uniform(-0.4, 0.4), 0.98), (0.3, 0.3, 0.18),
            rng.choice(["Hay", "ClothCream", "Planks"]))
    return p, {}


def cart():
    p = Part()
    box(p, (0, 0, 0.75), (2.6, 1.3, 0.1), "Planks")
    for s in (-1, 1):
        box(p, (0, s * 0.65, 1.0), (2.6, 0.08, 0.45), "Planks")
        cylinder(p, (0.2, s * 0.78, 0.6), 0.6, 0.1, "Timber", segments=14, rot=(90, 0, 0))
    box(p, (-1.25, 0, 1.0), (0.08, 1.3, 0.45), "Planks")
    for s in (-1, 1):
        box(p, (2.1, s * 0.35, 0.7), (1.8, 0.08, 0.08), "Timber")
    box(p, (0, 0, 1.0), (1.6, 1.0, 0.6), "Hay")
    return p, {}


def fence():
    p = Part()
    for x in (-1.0, 1.0):
        box(p, (x, 0, 0.55), (0.12, 0.12, 1.1), "Timber")
    for z in (0.45, 0.9):
        box(p, (0, 0, z), (2.1, 0.06, 0.1), "Planks")
    return p, {}


def barrel():
    p = Part()
    cylinder(p, (0, 0, 0.45), 0.33, 0.9, "Planks", segments=14)
    for z in (0.15, 0.75):
        cylinder(p, (0, 0, z), 0.345, 0.05, "Metal", segments=14)
    return p, {}


def crate():
    p = Part()
    box(p, (0, 0, 0.35), (0.7, 0.7, 0.7), "Planks")
    for s in (-1, 1):
        box(p, (0, s * 0.355, 0.35), (0.72, 0.02, 0.1), "Timber")
    return p, {}


def haybale():
    p = Part()
    cylinder(p, (0, 0, 0.65), 0.65, 1.2, "Hay", segments=16, rot=(90, 0, 0))
    return p, {}


def woodpile():
    p = Part()
    for row in range(3):
        for i in range(6 - row):
            cylinder(p, (0, -0.9 + i * 0.3 + row * 0.15, 0.15 + row * 0.26), 0.14, 1.2, "Bark", segments=8,
                     rot=(0, 90, 0))
    return p, {}


def bench():
    p = Part()
    box(p, (0, 0, 0.45), (1.8, 0.4, 0.07), "Planks")
    for x in (-0.75, 0.75):
        box(p, (x, 0, 0.22), (0.08, 0.35, 0.45), "Timber")
    return p, {}


def lamppost():
    p = Part()
    box(p, (0, 0, 1.6), (0.14, 0.14, 3.2), "Timber")
    box(p, (0.3, 0, 3.15), (0.7, 0.08, 0.08), "Timber")
    box(p, (0.6, 0, 2.9), (0.25, 0.25, 0.35), "Metal")
    return p, {}


def bridge():
    p = Part()
    for i in range(14):
        box(p, (0, -3.25 + i * 0.5, 0.55), (2.6, 0.45, 0.08), "Planks")
    for s in (-1, 1):
        box(p, (s * 1.25, 0, 0.35), (0.2, 7.2, 0.3), "Timber")
        for y in (-3.4, -1.2, 1.2, 3.4):
            box(p, (s * 1.3, y, 0.95), (0.12, 0.12, 1.0), "Timber")
        box(p, (s * 1.3, 0, 1.4), (0.08, 7.0, 0.1), "Timber")
    return p, {}


# ----------------------------------------------------------------------------
# Terrain, road, lake
# ----------------------------------------------------------------------------
def _hash(ix, iy, s):
    return (math.sin(ix * 127.1 + iy * 311.7 + s * 74.7) * 43758.5453) % 1.0


def _vnoise(x, y, s=0):
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    ux, uy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = _hash(ix, iy, s), _hash(ix + 1, iy, s)
    c, d = _hash(ix, iy + 1, s), _hash(ix + 1, iy + 1, s)
    return (a * (1 - ux) + b * ux) * (1 - uy) + (c * (1 - ux) + d * ux) * uy


def _fbm(x, y, s=0, octaves=4):
    v, amp, f = 0.0, 0.5, 1.0
    for o in range(octaves):
        v += amp * _vnoise(x * f, y * f, s + o * 17)
        amp *= 0.5
        f *= 2.03
    return v


def _smooth(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


LAKE = (78.0, 18.0, 24.0, 15.0)        # center x, y, radius x, radius y (m)


def terrain_height(x, y):
    """Flat village core, rolling hills, a lake basin, mountains on the horizon."""
    r = math.hypot(x / 1.15, y)
    hills = _fbm(x * 0.012, y * 0.012, 3) * 14.0 - 4.0
    h = _smooth(70, 150, r) * hills
    mount = _fbm(x * 0.006 + 10, y * 0.006, 9) * 1.4
    h += _smooth(220, 420, r) * (35 + 110 * mount)
    lx, ly, rx, ry = LAKE
    q = ((x - lx) / rx) ** 2 + ((y - ly) / ry) ** 2
    h -= 3.2 * (1 - _smooth(0.55, 1.25, q))
    return h


def terrain(size=900.0, n=180):
    p = Part()
    bm = bmesh.new()
    verts = []
    for j in range(n + 1):
        row = []
        for i in range(n + 1):
            # denser near the village: warp grid coordinates
            u = (i / n) * 2 - 1
            v = (j / n) * 2 - 1
            x = math.copysign(abs(u) ** 1.6, u) * size / 2
            y = math.copysign(abs(v) ** 1.6, v) * size / 2
            row.append(bm.verts.new((x, y, terrain_height(x, y))))
        verts.append(row)
    for j in range(n):
        for i in range(n):
            bm.faces.new((verts[j][i], verts[j][i + 1], verts[j + 1][i + 1], verts[j + 1][i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _obj_from_bm(bm, "terrain", "Grass")
    p.append(ob)
    return p, {}


def lake():
    p = Part()
    lx, ly, rx, ry = LAKE
    bm = bmesh.new()
    seg = 48
    c = bm.verts.new((lx, ly, -1.2))
    ring = [bm.verts.new((lx + rx * 1.15 * math.cos(2 * math.pi * k / seg), ly + ry * 1.15 * math.sin(2 * math.pi * k / seg),
                          -1.2)) for k in range(seg)]
    for k in range(seg):
        bm.faces.new((c, ring[k], ring[(k + 1) % seg]))
    p.append(_obj_from_bm(bm, "lake", "Water"))
    return p, {"water_z": -1.2}


ROAD = [(-95, -30), (-60, -14), (-30, -6), (0, 0), (28, 6), (55, 4), (68, 16), (78, 40), (90, 75)]
SIDE_ROAD = [(0, 0), (-6, 25), (-4, 52)]


def ribbon(points, width, material, z=0.04, sub=8):
    """Smooth road ribbon through points (Catmull-Rom)."""
    p = Part()
    pts = [Vector((x, y, 0)) for x, y in points]
    path = []
    for i in range(len(pts) - 1):
        p0 = pts[max(i - 1, 0)]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        for k in range(sub):
            t = k / sub
            t2, t3 = t * t, t * t * t
            path.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                               (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    path.append(pts[-1])
    bm = bmesh.new()
    left, right = [], []
    for i, q in enumerate(path):
        a = path[max(i - 1, 0)]
        b = path[min(i + 1, len(path) - 1)]
        tng = (b - a).normalized()
        nrm = Vector((-tng.y, tng.x, 0))
        hz = max(terrain_height(q.x, q.y), 0.0) + z
        left.append(bm.verts.new((q.x + nrm.x * width / 2, q.y + nrm.y * width / 2, hz)))
        right.append(bm.verts.new((q.x - nrm.x * width / 2, q.y - nrm.y * width / 2, hz)))
    for i in range(len(path) - 1):
        bm.faces.new((left[i], right[i], right[i + 1], left[i + 1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    p.append(_obj_from_bm(bm, "road", material))
    return p, path


def plaza():
    p = Part()
    cylinder(p, (0, 0, 0.03), 13.0, 0.08, "Cobble", segments=40)
    return p, {}


# ----------------------------------------------------------------------------
# Export
# ----------------------------------------------------------------------------
def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)


def join(parts, name):
    if not parts:
        return None
    ctx = bpy.context
    for ob in ctx.scene.objects:
        ob.select_set(False)
    for ob in parts:
        ob.select_set(True)
    ctx.view_layer.objects.active = parts[0]
    if len(parts) > 1:
        bpy.ops.object.join()
    ob = ctx.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    # merge duplicate material slots (joining keeps one slot per source object)
    slots = {}
    remap = {}
    for i, s in enumerate(ob.material_slots):
        key = s.material.name if s.material else "None"
        if key not in slots:
            slots[key] = len(slots)
        remap[i] = slots[key]
    me = ob.data
    names = list(slots.keys())
    if len(names) != len(me.materials):
        idx = [remap.get(poly.material_index, 0) for poly in me.polygons]
        me.materials.clear()
        for nm in names:
            me.materials.append(bpy.data.materials[nm])
        for poly, i in zip(me.polygons, idx):
            poly.material_index = i
    return ob


def export_fbx(ob, path):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, apply_unit_scale=True,
                             apply_scale_options="FBX_SCALE_UNITS", axis_forward="-Y", axis_up="Z",
                             mesh_smooth_type="FACE", use_mesh_modifiers=True, add_leaf_bones=False,
                             bake_anim=False, path_mode="AUTO")


def build_all(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    manifest = {}

    def emit(name, parts, meta=None, extra=None):
        clear_scene_keep = None
        ob = join(parts, name)
        export_fbx(ob, os.path.join(out_dir, name + ".fbx"))
        manifest[name] = meta or {}
        bpy.data.objects.remove(ob, do_unlink=True)

    house_defs = {
        "House_Cottage":   dict(w=7.0, d=5.6, floors=1, ground="Stone", roof="Thatch", pitch=52, timber=False, seed=1),
        "House_Timber2":   dict(w=8.5, d=6.5, floors=2, ground="Stone", upper="Plaster", roof="RoofShingle", pitch=52,
                                jetty=0.35, seed=2),
        "House_Timber2B":  dict(w=7.5, d=6.0, floors=2, ground="Plaster", upper="PlasterB", roof="RoofTile", pitch=48,
                                jetty=0.3, seed=3),
        "House_Long":      dict(w=12.0, d=6.5, floors=1, floor_h=3.2, ground="Planks", roof="RoofShingle", pitch=45,
                                timber=False, chimney=False, door_u=3.0, seed=4),
        "House_Hut":       dict(w=5.0, d=4.2, floors=1, floor_h=2.5, ground="Planks", roof="Thatch", pitch=55,
                                timber=False, seed=5),
        "House_Tavern":    dict(w=11.0, d=8.0, floors=2, floor_h=3.0, ground="Stone", upper="Plaster", roof="RoofTile",
                                pitch=50, jetty=0.4, seed=6),
        "House_Stone2":    dict(w=8.0, d=7.0, floors=2, ground="Stone", upper="Stone", roof="RoofSlate", pitch=45,
                                timber=False, seed=8),
    }
    for name, kw in house_defs.items():
        clear_scene()
        parts, glass, meta = house(name, **kw)
        emit(name + "_Glass", glass, {})
        emit(name, parts, meta)
    clear_scene()
    parts, glass, meta = church()
    emit("Church_Glass", glass, {})
    emit("Church", parts, meta)

    generators = [("Tree_Oak_%d" % i, lambda i=i: tree_oak(100 + i)) for i in range(4)]
    generators += [("Tree_Pine_%d" % i, lambda i=i: tree_pine(200 + i)) for i in range(3)]
    generators += [("Bush_%d" % i, lambda i=i: bush(300 + i)) for i in range(3)]
    generators += [("Rock_%d" % i, lambda i=i: rock(400 + i)) for i in range(3)]
    generators += [("Stall_Red", lambda: stall(1, "ClothRed")), ("Stall_Blue", lambda: stall(2, "ClothBlue")),
                   ("Stall_Cream", lambda: stall(3, "ClothCream")), ("Cart", cart), ("Fence", fence),
                   ("Barrel", barrel), ("Crate", crate), ("HayBale", haybale), ("WoodPile", woodpile),
                   ("Bench", bench), ("LampPost", lamppost), ("Bridge", bridge), ("Plaza", plaza),
                   ("Terrain", terrain), ("Lake", lake)]
    for name, gen in generators:
        clear_scene()
        parts, meta = gen()
        emit(name, parts, meta)
    clear_scene()
    p, water, meta = well()
    emit("Well_Water", water, {})
    emit("Well", p, meta)
    clear_scene()
    road, path = ribbon(ROAD, 5.0, "Dirt")
    emit("Road_Main", road, {"path": [[q.x, q.y] for q in path]})
    clear_scene()
    road2, path2 = ribbon(SIDE_ROAD, 3.5, "Dirt", z=0.05)
    emit("Road_Side", road2, {"path": [[q.x, q.y] for q in path2]})
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    return manifest


# ----------------------------------------------------------------------------
# Village layout (shared with Unreal)
# ----------------------------------------------------------------------------
def make_layout(manifest):
    rng = random.Random(2026)
    L = []

    def add(asset, x, y, yaw, heat, ttype, z=None, tags=(), label=None):
        zz = terrain_height(x, y) if z is None else z
        L.append({"asset": asset, "x": round(x, 2), "y": round(y, 2), "z": round(max(zz, -0.2) if z is None else zz, 2),
                  "yaw": round(yaw, 1), "heat": heat, "type": ttype, "tags": list(tags),
                  "label": label or asset})

    def face_road_yaw(x, y):
        # yaw so the house front (-Y) faces the nearest road point
        best = None
        for pts in (manifest["Road_Main"]["path"], manifest["Road_Side"]["path"]):
            for qx, qy in pts:
                dd = (qx - x) ** 2 + (qy - y) ** 2
                if best is None or dd < best[0]:
                    best = (dd, qx, qy)
        _, qx, qy = best
        ang = math.degrees(math.atan2(qy - y, qx - x))   # direction to road
        return ang + 90                                    # front (-Y) rotated to that direction

    add("Terrain", 0, 0, 0, 1, "Ground", z=0)
    add("Lake", 0, 0, 0, 0, "Water", z=0)
    add("Road_Main", 0, 0, 0, 1, "Ground", z=0)
    add("Road_Side", 0, 0, 0, 1, "Ground", z=0)
    add("Plaza", 0, 0, 0, 1, "Ground", z=0)
    add("Well", -4.5, 3.0, 0, 1, "Building", z=0)
    add("Well_Water", -4.5, 3.0, 0, 0, "Water", z=0)
    add("Church", -5.0, 40.0, 0, 2, "Building", z=0, label="Church")
    add("Church_Glass", -5.0, 40.0, 0, 0, "Glass", z=0, label="Church_Glass")

    # houses along the main road (both sides) and the side road
    spots = [(-78, -40, "House_Timber2"), (-70, -6, "House_Cottage"), (-55, -26, "House_Long"),
             (-44, 1, "House_Timber2B"), (-36, -20, "House_Stone2"), (-22, 10, "House_Cottage"),
             (-18, -17, "House_Tavern"), (17, -13, "House_Timber2"), (20, 18, "House_Timber2B"),
             (38, -8, "House_Stone2"), (40, 18, "House_Hut"), (55, -10, "House_Cottage"),
             (47, 35, "House_Timber2"), (-17, 28, "House_Hut"), (9, 33, "House_Long"),
             (-20, 50, "House_Cottage"), (12, 55, "House_Timber2B")]
    for i, (x, y, asset) in enumerate(spots):
        yaw = face_road_yaw(x, y)
        burning = (asset == "House_Timber2" and i == 7)
        lab = "House_%02d%s" % (i, "_Burning" if burning else "")
        add(asset, x, y, yaw, 3 if burning else 2, "Building", tags=(["Burning"] if burning else []), label=lab)
        add(asset + "_Glass", x, y, yaw, 0, "Glass", label=lab + "_Glass")
        # props near each house
        for k in range(rng.randint(1, 3)):
            px, py = x + rng.uniform(-5, 5), y + rng.uniform(-5, 5)
            if math.hypot(px, py) > 15:
                add(rng.choice(["Barrel", "Crate", "WoodPile", "Bench"]), px, py, rng.uniform(0, 360), 1, "Debris")

    # market on the plaza
    for (x, y, a, st) in ((6, -6, 20, "Stall_Red"), (9, 2, 100, "Stall_Blue"), (-8, -7, 330, "Stall_Cream")):
        add(st, x, y, a, 1, "Debris")
    add("Cart", -9, 6, 40, 1, "Debris")
    for (x, y) in ((-12, -3), (12, 4), (30, 5), (-35, -6), (52, 6)):
        add("LampPost", x, y, rng.uniform(0, 360), 1, "Debris")

    # fields with fences and hay
    for i in range(10):
        add("Fence", -40 + i * 2.1, 64, 0, 1, "Debris")
        add("Fence", 30 + i * 2.1, -30, 0, 1, "Debris")
    for i in range(6):
        add("HayBale", 33 + rng.uniform(0, 18), -40 + rng.uniform(-6, 4), rng.uniform(0, 180), 1, "Debris")

    # trees: orchard + forest belt + lakeside
    for i in range(90):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(85, 170)
        x, y = math.cos(a) * r * 1.1, math.sin(a) * r
        lx, ly, rx, ry = LAKE
        if ((x - lx) / rx) ** 2 + ((y - ly) / ry) ** 2 < 1.6:
            continue
        add(rng.choice(["Tree_Pine_0", "Tree_Pine_1", "Tree_Pine_2", "Tree_Oak_0", "Tree_Oak_1"]), x, y,
            rng.uniform(0, 360), 1, "Vegetation")
    for i in range(30):
        x, y = rng.uniform(-75, 75), rng.uniform(-60, 75)
        near_house = any(math.hypot(x - sx, y - sy) < 9 for sx, sy, _ in spots)
        near_road = min(math.hypot(x - qx, y - qy) for qx, qy in manifest["Road_Main"]["path"]) < 6
        if near_house or near_road or math.hypot(x, y) < 16 or math.hypot(x + 5, y - 40) < 16:
            continue
        add(rng.choice(["Tree_Oak_0", "Tree_Oak_1", "Tree_Oak_2", "Tree_Oak_3"]), x, y, rng.uniform(0, 360), 1,
            "Vegetation")
    for i in range(40):
        x, y = rng.uniform(-80, 80), rng.uniform(-60, 80)
        if any(math.hypot(x - sx, y - sy) < 6 for sx, sy, _ in spots) or math.hypot(x, y) < 14:
            continue
        add(rng.choice(["Bush_0", "Bush_1", "Bush_2", "Rock_0", "Rock_1", "Rock_2"]), x, y, rng.uniform(0, 360), 1,
            "Vegetation")
    return L


def preview(out_dir, manifest, layout, cam_loc, cam_target, name, res=(1280, 720), samples=24, lens=24):
    """Instantiate the layout in Blender and render one Cycles image."""
    clear_scene()
    import_cache = {}
    for item in layout:
        a = item["asset"]
        if a not in import_cache:
            bpy.ops.import_scene.fbx(filepath=os.path.join(out_dir, a + ".fbx"))
            ob = bpy.context.selected_objects[0]
            for i, slot in enumerate(ob.data.materials):
                if slot is not None:
                    ob.data.materials[i] = mat(slot.name.split(".")[0])
            ob.hide_render = True
            ob.hide_viewport = True
            import_cache[a] = ob
        src = import_cache[a]
        inst = bpy.data.objects.new(item["label"], src.data)
        bpy.context.scene.collection.objects.link(inst)
        inst.location = (item["x"], item["y"], item["z"])
        inst.rotation_euler = (0, 0, math.radians(item["yaw"]))
        inst.scale = src.scale
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.samples = samples
    scn.cycles.device = "CPU"
    scn.render.resolution_x, scn.render.resolution_y = res
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    scn.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.55, 0.7, 0.95, 1)
    bg.inputs[1].default_value = 0.8
    sun_data = bpy.data.lights.new("sun", "SUN")
    sun_data.energy = 3.0
    scn.view_settings.view_transform = "AgX"
    try:
        scn.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    scn.view_settings.exposure = -0.3
    if not any(it["asset"] == "Terrain" for it in layout):
        gp = Part()
        box(gp, (0, 0, -0.05), (2000, 2000, 0.1), "Grass")
    sun = bpy.data.objects.new("sun", sun_data)
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(35))
    scn.collection.objects.link(sun)
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = lens
    cam_data.clip_end = 2000
    cam = bpy.data.objects.new("cam", cam_data)
    scn.collection.objects.link(cam)
    cam.location = cam_loc
    direction = Vector(cam_target) - Vector(cam_loc)
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scn.camera = cam
    scn.render.filepath = os.path.join(out_dir, name)
    bpy.ops.render.render(write_still=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--asset-preview", default="")
    args = ap.parse_args(argv)
    manifest = build_all(args.out)
    layout = make_layout(manifest)
    with open(os.path.join(args.out, "layout.json"), "w") as f:
        json.dump(layout, f, indent=0)
    # terrain height grid (2 m steps, -150..150 m) so Unreal can stand people/fires on the ground
    step, half = 2.0, 150.0
    n = int(2 * half / step) + 1
    grid = [[round(max(terrain_height(-half + i * step, -half + j * step), -3.0), 3) for i in range(n)] for j in range(n)]
    with open(os.path.join(args.out, "heights.json"), "w") as f:
        json.dump({"origin": -half, "step": step, "n": n, "rows_y_cols_x": grid}, f)
    print("assets:", len(manifest), "layout items:", len(layout))
    if args.preview:
        preview(args.out, manifest, layout, (10, -75, 32), (5, 10, 0), "preview_overview.png")
    if args.asset_preview:
        names = args.asset_preview.split(",")
        items = []
        for i, n in enumerate(names):
            items.append({"asset": n, "x": i * 24.0, "y": 0, "z": 0, "yaw": 0, "label": n})
            if n + "_Glass" in manifest:
                items.append({"asset": n + "_Glass", "x": i * 24.0, "y": 0, "z": 0, "yaw": 0, "label": n + "_G"})
        preview(args.out, manifest, items, ((len(names) - 1) * 12.0 - 6, -22 - 8 * len(names), 10),
                ((len(names) - 1) * 12.0, 0, 5),
                "preview_assets.png", res=(1600, 600), lens=35)


if __name__ == "__main__":
    main()
