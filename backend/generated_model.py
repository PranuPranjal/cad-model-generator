import cadquery as cq
from cadquery import exporters

result = cq.Workplane().sphere(10)
exporters.export(result, 'output.stl')