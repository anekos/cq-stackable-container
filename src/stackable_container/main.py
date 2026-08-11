from math import acos, cos, sin

import cadquery as cq
from click_cadquery.git import version_number as ver
from pydantic import BaseModel

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

    @property
    def filename(self) -> str:
        return f"v{ver()}-{self.width}w{self.height}h{self.depth}d{self.thickness}t.stl"


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

    return outer.faces(">Z").shell(-t)
