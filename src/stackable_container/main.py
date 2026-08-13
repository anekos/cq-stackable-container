from functools import reduce
from math import acos, cos, sin

import cadquery as cq
from click_cadquery.git import version_number as ver
from pydantic import BaseModel, Field

# Proportions read off the reference model (sample.stl: 120 x 120 x 80, t = 2).
CORNER_RADIUS_RATIO = 2.0  # vertical corner fillet
BOTTOM_RADIUS_RATIO = 0.5  # fillet along the bottom face
CLEARANCE_RATIO = 0.2  # play between the foot and the cavity it drops into
BLEND_RADIUS_RATIO = 1.5  # the two arcs of the S-shaped step
LIP_HEIGHT = 11.0  # bottom face -> middle of the step
BLEND_STEPS = 8  # sections used to loft one arc of the step


class Param(BaseModel):
    width: int = 120
    height: int = 80
    depth: int = 120
    thickness: float = 2.0
    dividers_x: int = Field(default=0, ge=0)  # walls running along Y, splitting X
    dividers_y: int = Field(default=0, ge=0)  # walls running along X, splitting Y

    @property
    def filename(self) -> str:
        name = f"v{ver()}-{self.width}w{self.height}h{self.depth}d{self.thickness}t"
        if self.dividers_x or self.dividers_y:
            name += f"-{self.dividers_x}x{self.dividers_y}y"
        return f"{name}.stl"


def _section(width: float, depth: float, radius: float) -> cq.Sketch:
    return cq.Sketch().rect(width, depth).vertices().fillet(radius)


def _at(sketch: cq.Sketch, z: float) -> cq.Sketch:
    return sketch.moved(cq.Location(cq.Vector(0, 0, z)))


def _prism(section: cq.Sketch, z0: float, z1: float) -> cq.Workplane:
    return cq.Workplane("XY").placeSketch(_at(section, z0)).extrude(z1 - z0)


def _step_profile(inset: float, blend: float) -> list[tuple[float, float]]:
    """(inward offset, z relative to the middle of the step) along the S-curve.

    Two tangent arcs of radius ``blend``: the upper one peels away from the body
    wall, the lower one lands tangentially on the foot wall.
    """
    theta = acos(1.0 - inset / (2.0 * blend))
    half = blend * sin(theta)

    upper = [
        (blend * (1.0 - cos(a)), half - blend * sin(a))
        for a in (theta * i / BLEND_STEPS for i in range(BLEND_STEPS + 1))
    ]
    lower = [(inset - d, -z) for d, z in reversed(upper)]
    return upper + lower[1:]


def _nesting_depth(inset: float, blend: float, clearance: float) -> float:
    """How deep the foot of a stacked container sinks below this one's rim.

    The container above slides down until its S-curve meets the inner edge of
    the rim, i.e. where the curve has pulled in by exactly one wall thickness.
    """
    theta = acos(1.0 - inset / (2.0 * blend))
    contact = acos(1.0 - clearance / blend)
    return LIP_HEIGHT - blend * (sin(theta) - sin(contact))


def _divider_offsets(inner: float, count: int, thickness: float) -> list[float]:
    """Centres of ``count`` dividers cutting ``inner`` into equal compartments."""
    cell = (inner - count * thickness) / (count + 1)
    if cell <= 0.0:
        raise ValueError(f"{count} dividers do not fit in {inner}")
    return [
        (i + 1) * (cell + thickness) - thickness / 2 - inner / 2 for i in range(count)
    ]


def _dividers(param: Param, top: float) -> cq.Workplane:
    t = param.thickness
    plates = [
        cq.Workplane("XY")
        .box(t, param.depth, top - t, centered=(True, True, False))
        .translate((x, 0.0, t))
        for x in _divider_offsets(param.width - 2 * t, param.dividers_x, t)
    ] + [
        cq.Workplane("XY")
        .box(param.width, t, top - t, centered=(True, True, False))
        .translate((0.0, y, t))
        for y in _divider_offsets(param.depth - 2 * t, param.dividers_y, t)
    ]
    return reduce(lambda a, b: a.union(b), plates)


def build(param: Param) -> cq.Workplane:
    t = param.thickness
    corner = t * CORNER_RADIUS_RATIO
    inset = t * (1.0 + CLEARANCE_RATIO)
    blend = t * BLEND_RADIUS_RATIO

    profile = _step_profile(inset, blend)
    step_top = LIP_HEIGHT + profile[0][1]
    step_bottom = LIP_HEIGHT + profile[-1][1]

    body = _section(param.width, param.depth, corner)
    foot = _section(param.width - 2 * inset, param.depth - 2 * inset, corner)

    step = (
        cq.Workplane("XY")
        .placeSketch(
            *(
                _at(
                    _section(param.width - 2 * d, param.depth - 2 * d, corner),
                    LIP_HEIGHT + z,
                )
                for d, z in profile
            )
        )
        .loft(ruled=False)
    )

    outer = (
        _prism(foot, 0.0, step_bottom)
        .union(step)
        .union(_prism(body, step_top, param.height))
    )

    outer = outer.faces("<Z").edges().fillet(t * BOTTOM_RADIUS_RATIO)

    result = outer.faces(">Z").shell(-t)

    if param.dividers_x or param.dividers_y:
        clearance = t * CLEARANCE_RATIO
        # Stop below the foot of whatever gets stacked on top of this one.
        top = param.height - _nesting_depth(inset, blend, clearance) - clearance
        # Trimmed by the outer body: the plates span the full footprint so that
        # they always reach the wall, which is narrower down around the foot.
        result = result.union(_dividers(param, top).intersect(outer))

    return result
