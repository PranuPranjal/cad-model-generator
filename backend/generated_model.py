from cq_warehouse import fastener
from cadquery import exporters
result = fastener.ButtonHeadScrew(size="M3-0.5", length=3, fastener_type="iso7380_1", hand="right", simple=True)
exporters.export(result, "screw.stl")
exporters.export(result, "screw.step")