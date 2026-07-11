// HALO Factory Floor — dependency graph visualization (FF-R3)
// Uses D3.js force-directed graph (loaded from CDN)
// Specs are nodes colored by status, dependency edges connect them

const STATUS_COLORS = {
    'draft': '#8b949e',
    'ready': '#3fb950',
    'in_progress': '#58a6ff',
    'implemented': '#a371f7',
    'merged': '#ffffff',
    'failed_red': '#f85149',
    'failed_green': '#da3633',
    'failed_e2e': '#f85149',
};

function renderGraph(specs) {
    const container = document.getElementById('graph-container');
    if (!container) return;

    container.innerHTML = '';

    if (!specs || specs.length === 0) {
        container.innerHTML = '<p class="empty-state">No specs to display. Create specs with depends_on or blocks to see the dependency graph.</p>';
        return;
    }

    if (typeof d3 === 'undefined') {
        container.innerHTML = '<p class="empty-state">D3.js not loaded. Add the CDN script tag to index.html.</p>';
        return;
    }

    const width = container.clientWidth || 800;
    const height = 500;

    const svg = d3.select(container).append('svg')
        .attr('width', width)
        .attr('height', height)
        .attr('class', 'graph-svg');

    container._svg = svg;

    const nodes = specs.map(s => ({
        id: s.id,
        title: s.title || s.id,
        status: s.status || 'draft',
        project: s.project || '',
    }));

    const nodeIds = new Set(nodes.map(n => n.id));
    const links = [];

    specs.forEach(s => {
        if (s.depends_on) {
            s.depends_on.forEach(dep => {
                if (nodeIds.has(dep)) {
                    links.push({ source: dep, target: s.id, type: 'depends' });
                }
            });
        }
        if (s.blocks) {
            s.blocks.forEach(blocked => {
                if (nodeIds.has(blocked)) {
                    links.push({ source: s.id, target: blocked, type: 'blocks' });
                }
            });
        }
    });

    if (nodeIds.size === 1 && links.length === 0) {
        const n = nodes[0];
        const g = svg.append('g');
        g.append('circle')
            .attr('cx', width / 2)
            .attr('cy', height / 2)
            .attr('r', 30)
            .attr('fill', STATUS_COLORS[n.status] || '#8b949e')
            .attr('stroke', '#30363d')
            .attr('stroke-width', 2);
        g.append('text')
            .attr('x', width / 2)
            .attr('y', height / 2 + 50)
            .attr('text-anchor', 'middle')
            .attr('fill', '#c9d1d9')
            .attr('font-size', '13px')
            .text(n.id);
        return;
    }

    const simulation = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(links).id(d => d.id).distance(100))
        .force('charge', d3.forceManyBody().strength(-300))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(40));

    const linkGroup = svg.append('g').attr('class', 'links');
    const nodeGroup = svg.append('g').attr('class', 'nodes');

    const link = linkGroup.selectAll('line')
        .data(links)
        .enter().append('line')
        .attr('stroke', d => d.type === 'blocks' ? '#f85149' : '#30363d')
        .attr('stroke-width', d => d.type === 'blocks' ? 2 : 1)
        .attr('stroke-dasharray', d => d.type === 'blocks' ? '5,5' : null)
        .attr('marker-end', 'url(#arrow)');

    const arrowDef = svg.append('defs').append('marker')
        .attr('id', 'arrow')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 20)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', '#30363d');

    const node = nodeGroup.selectAll('g')
        .data(nodes)
        .enter().append('g')
        .attr('class', 'node')
        .call(d3.drag()
            .on('start', (event, d) => {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            })
            .on('drag', (event, d) => {
                d.fx = event.x;
                d.fy = event.y;
            })
            .on('end', (event, d) => {
                if (!event.active) simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            }));

    node.append('circle')
        .attr('r', 25)
        .attr('fill', d => STATUS_COLORS[d.status] || '#8b949e')
        .attr('stroke', '#30363d')
        .attr('stroke-width', 2);

    node.append('text')
        .attr('dy', 35)
        .attr('text-anchor', 'middle')
        .attr('fill', '#c9d1d9')
        .attr('font-size', '12px')
        .text(d => d.id);

    simulation.on('tick', () => {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);
        node.attr('transform', d => `translate(${d.x},${d.y})`);
    });
}

export { renderGraph };