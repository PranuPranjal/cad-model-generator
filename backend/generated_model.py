import cadquery as cq
from cadquery import exporters

result = cq.Workplane().sphere(20)
exporters.export(result, 'output.stl')