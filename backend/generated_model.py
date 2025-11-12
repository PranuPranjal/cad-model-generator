from cadquery import exporters
import cadquery as cq
from cq_warehouse.bearing import SingleRowCappedDeepGrooveBallBearing
result = SingleRowCappedDeepGrooveBallBearing(size="M5-13-4", bearing_type="SKT", simple = False)
exporters.export(result, "screw.stl")
exporters.export(result, "screw.step")