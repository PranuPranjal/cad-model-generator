from cadquery import exporters
import cadquery as cq
from cq_warehouse.fastener import HexHeadWithFlangeScrew
result = HexHeadWithFlangeScrew(size="M5-0.8", length=3, fastener_type="din1662", hand="left", simple=True)
exporters.export(result, "screw.stl")
exporters.export(result, "screw.step")