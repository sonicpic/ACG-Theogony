"""导出端点：GraphML（Gephi）/ CSV。PNG/SVG 在前端生成。"""

from __future__ import annotations

import csv
import io
import xml.sax.saxutils as sx

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from theogony.core.enums import RELATION_META
from theogony.core.graph import GraphService

router = APIRouter(tags=["exports"], include_in_schema=True)


def _current_graph():
    gs = GraphService.instance()
    snap = gs.snapshot
    nodes = {cid: c for cid, c in snap.characters.items()}
    edges = [(s, t, rt) for s, t, rt, _ in snap.edges]
    return nodes, edges


@router.get("/export/graphml", response_class=PlainTextResponse)
def export_graphml():
    nodes, edges = _current_graph()
    out = io.StringIO()
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    out.write(
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns"\n'
        '         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        '         xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns\n'
        '         http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">\n'
    )
    out.write('  <key id="d_name" for="node" attr.name="name" attr.type="string"/>\n')
    out.write('  <key id="d_myth" for="node" attr.name="mythology" attr.type="string"/>\n')
    out.write('  <key id="d_class" for="node" attr.name="class" attr.type="string"/>\n')
    out.write('  <key id="e_type" for="edge" attr.name="relationship" attr.type="string"/>\n')
    out.write('  <graph id="theogony" edgedefault="undirected">\n')
    for cid, c in nodes.items():
        out.write(f'    <node id="{sx.escape(cid)}">\n')
        out.write(f'      <data key="d_name">{sx.escape(c.name)}</data>\n')
        out.write(f'      <data key="d_myth">{sx.escape(c.mythology or "")}</data>\n')
        out.write(f'      <data key="d_class">{sx.escape(c.class_name)}</data>\n')
        out.write("    </node>\n")
    for i, (s, t, rt) in enumerate(edges):
        out.write(f'    <edge id="e{i}" source="{sx.escape(s)}" target="{sx.escape(t)}">\n')
        out.write(f'      <data key="e_type">{sx.escape(rt)}</data>\n')
        out.write("    </edge>\n")
    out.write("  </graph>\n</graphml>\n")
    return PlainTextResponse(out.getvalue(), media_type="application/xml", headers={
        "Content-Disposition": 'attachment; filename="theogony.graphml"'
    })


@router.get("/export/csv", response_class=PlainTextResponse)
def export_csv():
    nodes, edges = _current_graph()
    label = {t: m["label"] for t, m in RELATION_META.items()}
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["source_id", "source_name", "target_id", "target_name", "relationship", "关系"])
    for s, t, rt in edges:
        writer.writerow(
            [s, nodes[s].name if s in nodes else s, t, nodes[t].name if t in nodes else t, rt, label.get(rt, rt)]
        )
    return PlainTextResponse(out.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": 'attachment; filename="theogony_relationships.csv"'
    })


@router.get("/export/nodes", response_class=PlainTextResponse)
def export_nodes(limit: int = Query(default=1000, le=5000)):
    gs = GraphService.instance()
    snap = gs.snapshot
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["id", "name", "class", "mythology", "gender", "alignment", "degree", "image_url"])
    for cid, c in sorted(snap.characters.items(), key=lambda kv: kv[1].wiki_id)[:limit]:
        writer.writerow([cid, c.name, c.class_name, c.mythology or "", c.gender, c.alignment, gs.degree(cid), c.image_url])
    return PlainTextResponse(out.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": 'attachment; filename="theogony_characters.csv"'
    })
