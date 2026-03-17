/**
 * OraclePageIndex -- D3.js Force-Directed Knowledge Graph
 *
 * Fetches graph data from /api/graph and renders an interactive
 * force-directed visualization with search, highlight, and detail panel.
 */
(function () {
    "use strict";

    // ---------------------------------------------------------------
    // Constants
    // ---------------------------------------------------------------
    const NODE_COLORS = {
        document: "#58a6ff",
        section:  "#3fb950",
        entity:   "#d29922",
    };

    const NODE_RADIUS = {
        document: 16,
        section:  10,
        entity:   8,
    };

    const LABEL_MAX = 25;

    // Demo data used when the API is unavailable (local dev without Oracle)
    const DEMO_DATA = {
        nodes: [
            { id: "doc_1",  type: "document", label: "Oracle Database 23ai Guide",  summary: "Comprehensive guide to Oracle Database 23ai features.", description: "Covers SQL, PL/SQL, JSON, vectors, and property graphs." },
            { id: "sec_1",  type: "section",  label: "SQL Property Graphs",         summary: "Introduction to SQL property graph support in Oracle.", node_id: "1.1" },
            { id: "sec_2",  type: "section",  label: "AI Vector Search",            summary: "Oracle AI Vector Search enables similarity queries.", node_id: "1.2" },
            { id: "ent_1",  type: "entity",   label: "GRAPH_TABLE",                 entity_type: "SQL_CONSTRUCT", description: "SQL/PGQ function for querying property graphs." },
            { id: "ent_2",  type: "entity",   label: "VECTOR datatype",             entity_type: "FEATURE",      description: "Native vector datatype for storing embeddings." },
        ],
        edges: [
            { source: "doc_1", target: "sec_1", type: "contains" },
            { source: "doc_1", target: "sec_2", type: "contains" },
            { source: "sec_1", target: "sec_2", type: "parent_of" },
            { source: "sec_1", target: "ent_1", type: "mentions",   relevance: "DEFINES" },
            { source: "sec_2", target: "ent_2", type: "mentions",   relevance: "EXPLAINS" },
            { source: "ent_1", target: "ent_2", type: "related_to", relationship: "COMPLEMENTS" },
        ],
    };

    // ---------------------------------------------------------------
    // DOM References
    // ---------------------------------------------------------------
    const svg           = d3.select("#graph-svg");
    const searchInput   = document.getElementById("search-input");
    const resetBtn      = document.getElementById("reset-btn");
    const layoutToggle  = document.getElementById("layout-toggle");
    const detailsPanel  = document.getElementById("details-panel");
    const detailsClose  = document.getElementById("details-close");
    const statsText     = document.getElementById("stats-text");

    // ---------------------------------------------------------------
    // State
    // ---------------------------------------------------------------
    let graphData   = null;   // { nodes, edges }
    let simulation  = null;
    let linkSel     = null;
    let nodeSel     = null;
    let currentLayout = "force";
    let selectedNode  = null;

    // ---------------------------------------------------------------
    // Boot
    // ---------------------------------------------------------------
    async function init() {
        graphData = await fetchGraphData();
        updateStats();
        buildGraph();
        bindControls();
        initTimelineControls();
    }

    // ---------------------------------------------------------------
    // Data fetching
    // ---------------------------------------------------------------
    async function fetchGraphData() {
        try {
            const res = await fetch("/api/graph");
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            if (data.nodes && data.nodes.length > 0) {
                console.log(`Loaded ${data.nodes.length} nodes, ${data.edges.length} edges from API`);
                return data;
            }
            throw new Error("Empty graph");
        } catch (err) {
            console.warn("API unavailable, using demo data:", err.message);
            // Deep-clone demo data so D3 mutation doesn't affect the template
            return JSON.parse(JSON.stringify(DEMO_DATA));
        }
    }

    // ---------------------------------------------------------------
    // Stats
    // ---------------------------------------------------------------
    function updateStats() {
        const n = graphData.nodes.length;
        const e = graphData.edges.length;
        const docs = graphData.nodes.filter(d => d.type === "document").length;
        const secs = graphData.nodes.filter(d => d.type === "section").length;
        const ents = graphData.nodes.filter(d => d.type === "entity").length;
        statsText.textContent =
            `${n} nodes (${docs} docs, ${secs} sections, ${ents} entities) \u00B7 ${e} edges`;
    }

    // ---------------------------------------------------------------
    // Build D3 graph
    // ---------------------------------------------------------------
    function buildGraph() {
        svg.selectAll("*").remove();

        const width  = window.innerWidth;
        const height = window.innerHeight - 56; // minus header

        svg.attr("viewBox", [0, 0, width, height]);

        // Container group for zoom/pan
        const g = svg.append("g").attr("class", "graph-container");

        // Zoom behavior
        const zoom = d3.zoom()
            .scaleExtent([0.15, 5])
            .on("zoom", (event) => g.attr("transform", event.transform));

        svg.call(zoom);

        // Store zoom reference for reset
        svg.__zoom_behavior = zoom;
        svg.__container = g;

        // Arrow markers for directed edges
        const defs = svg.append("defs");
        ["parent_of", "contains", "mentions", "related_to"].forEach(type => {
            defs.append("marker")
                .attr("id", `arrow-${type}`)
                .attr("viewBox", "0 -4 8 8")
                .attr("refX", 20)
                .attr("refY", 0)
                .attr("markerWidth", 6)
                .attr("markerHeight", 6)
                .attr("orient", "auto")
                .append("path")
                .attr("d", "M0,-3L7,0L0,3")
                .attr("fill", getEdgeColor(type));
        });

        // Links
        linkSel = g.append("g")
            .attr("class", "links")
            .selectAll("line")
            .data(graphData.edges)
            .join("line")
            .attr("class", d => `link ${d.type || ""}`)
            .attr("marker-end", d => `url(#arrow-${d.type || "contains"})`);

        // Node groups
        nodeSel = g.append("g")
            .attr("class", "nodes")
            .selectAll("g")
            .data(graphData.nodes, d => d.id)
            .join("g")
            .attr("class", d => `node ${d.type || ""}`)
            .call(dragBehavior())
            .on("click", onNodeClick);

        // Circles
        nodeSel.append("circle")
            .attr("r", d => NODE_RADIUS[d.type] || 8);

        // Labels
        nodeSel.append("text")
            .attr("dx", d => (NODE_RADIUS[d.type] || 8) + 4)
            .attr("dy", "0.35em")
            .text(d => truncate(d.label, LABEL_MAX));

        // Tooltip on hover
        nodeSel.append("title")
            .text(d => d.label);

        // Simulation
        simulation = d3.forceSimulation(graphData.nodes)
            .force("link", d3.forceLink(graphData.edges)
                .id(d => d.id)
                .distance(80))
            .force("charge", d3.forceManyBody().strength(-200))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collide", d3.forceCollide().radius(d => (NODE_RADIUS[d.type] || 8) + 6))
            .on("tick", ticked);

        // Background click resets
        svg.on("click", onBackgroundClick);

        // Handle window resize
        window.addEventListener("resize", onResize);
    }

    function ticked() {
        linkSel
            .attr("x1", d => d.source.x)
            .attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x)
            .attr("y2", d => d.target.y);

        nodeSel.attr("transform", d => `translate(${d.x},${d.y})`);
    }

    // ---------------------------------------------------------------
    // Drag
    // ---------------------------------------------------------------
    function dragBehavior() {
        return d3.drag()
            .on("start", (event, d) => {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            })
            .on("drag", (event, d) => {
                d.fx = event.x;
                d.fy = event.y;
            })
            .on("end", (event, d) => {
                if (!event.active) simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            });
    }

    // ---------------------------------------------------------------
    // Interaction: Node click
    // ---------------------------------------------------------------
    function onNodeClick(event, d) {
        event.stopPropagation();

        selectedNode = d;

        // Find connected node IDs
        const connectedIds = new Set([d.id]);
        const connections = [];

        graphData.edges.forEach(e => {
            const srcId = typeof e.source === "object" ? e.source.id : e.source;
            const tgtId = typeof e.target === "object" ? e.target.id : e.target;

            if (srcId === d.id) {
                connectedIds.add(tgtId);
                const targetNode = graphData.nodes.find(n => n.id === tgtId);
                connections.push({
                    label: targetNode ? targetNode.label : tgtId,
                    type: e.type || "",
                    relevance: e.relevance || e.relationship || "",
                    direction: "outgoing",
                });
            }
            if (tgtId === d.id) {
                connectedIds.add(srcId);
                const sourceNode = graphData.nodes.find(n => n.id === srcId);
                connections.push({
                    label: sourceNode ? sourceNode.label : srcId,
                    type: e.type || "",
                    relevance: e.relevance || e.relationship || "",
                    direction: "incoming",
                });
            }
        });

        // Dim non-connected
        nodeSel.classed("dimmed", n => !connectedIds.has(n.id));
        nodeSel.classed("highlighted", n => n.id === d.id);
        linkSel.classed("dimmed", e => {
            const srcId = typeof e.source === "object" ? e.source.id : e.source;
            const tgtId = typeof e.target === "object" ? e.target.id : e.target;
            return !(connectedIds.has(srcId) && connectedIds.has(tgtId));
        });

        // Populate details panel
        showDetails(d, connections);
    }

    // ---------------------------------------------------------------
    // Interaction: Background click
    // ---------------------------------------------------------------
    function onBackgroundClick(event) {
        // Only reset if the click is on the SVG background itself
        if (event.target.tagName === "svg" || event.target === svg.node()) {
            resetHighlight();
            hideDetails();
        }
    }

    // ---------------------------------------------------------------
    // Details Panel
    // ---------------------------------------------------------------
    function showDetails(d, connections) {
        document.getElementById("detail-label").textContent = d.label;

        const typeBadge = document.getElementById("detail-type");
        typeBadge.textContent = d.type;
        typeBadge.className = `detail-value badge ${d.type}`;

        // Entity type
        const entityRow = document.getElementById("detail-entity-type-row");
        if (d.entity_type) {
            document.getElementById("detail-entity-type").textContent = d.entity_type;
            entityRow.style.display = "";
        } else {
            entityRow.style.display = "none";
        }

        // Node ID
        const nodeIdRow = document.getElementById("detail-node-id-row");
        if (d.node_id) {
            document.getElementById("detail-node-id").textContent = d.node_id;
            nodeIdRow.style.display = "";
        } else {
            nodeIdRow.style.display = "none";
        }

        // Summary
        const summarySection = document.getElementById("detail-summary-section");
        if (d.summary) {
            document.getElementById("detail-summary").textContent = d.summary;
            summarySection.style.display = "";
        } else {
            summarySection.style.display = "none";
        }

        // Description
        const descSection = document.getElementById("detail-description-section");
        if (d.description) {
            document.getElementById("detail-description").textContent = d.description;
            descSection.style.display = "";
        } else {
            descSection.style.display = "none";
        }

        // Connections list
        const connList = document.getElementById("detail-connections");
        connList.innerHTML = "";
        if (connections.length === 0) {
            document.getElementById("detail-connections-section").style.display = "none";
        } else {
            document.getElementById("detail-connections-section").style.display = "";
            connections.forEach(c => {
                const li = document.createElement("li");
                const arrow = c.direction === "outgoing" ? "\u2192" : "\u2190";
                const typeSpan = document.createElement("span");
                typeSpan.className = "conn-type";
                typeSpan.textContent = c.type.replace(/_/g, " ");
                const text = document.createTextNode(` ${arrow} ${c.label}`);
                li.appendChild(typeSpan);
                li.appendChild(text);
                if (c.relevance) {
                    const rel = document.createTextNode(` (${c.relevance})`);
                    li.appendChild(rel);
                }
                connList.appendChild(li);
            });
        }

        detailsPanel.classList.remove("hidden");
    }

    function hideDetails() {
        detailsPanel.classList.add("hidden");
        selectedNode = null;
    }

    // ---------------------------------------------------------------
    // Highlight / Dim
    // ---------------------------------------------------------------
    function resetHighlight() {
        nodeSel.classed("dimmed", false);
        nodeSel.classed("highlighted", false);
        linkSel.classed("dimmed", false);
        selectedNode = null;
    }

    // ---------------------------------------------------------------
    // Search
    // ---------------------------------------------------------------
    function onSearch(query) {
        if (!query || query.trim() === "") {
            resetHighlight();
            return;
        }

        const q = query.toLowerCase();
        const matchIds = new Set();

        graphData.nodes.forEach(n => {
            if (n.label && n.label.toLowerCase().includes(q)) {
                matchIds.add(n.id);
            }
        });

        if (matchIds.size === 0) {
            // Dim everything if no matches
            nodeSel.classed("dimmed", true);
            linkSel.classed("dimmed", true);
            return;
        }

        nodeSel.classed("dimmed", n => !matchIds.has(n.id));
        nodeSel.classed("highlighted", n => matchIds.has(n.id));
        linkSel.classed("dimmed", e => {
            const srcId = typeof e.source === "object" ? e.source.id : e.source;
            const tgtId = typeof e.target === "object" ? e.target.id : e.target;
            return !(matchIds.has(srcId) && matchIds.has(tgtId));
        });
    }

    // ---------------------------------------------------------------
    // Layout toggle
    // ---------------------------------------------------------------
    function switchLayout(layout) {
        currentLayout = layout;

        const width  = window.innerWidth;
        const height = window.innerHeight - 56;

        if (layout === "tree") {
            // Arrange nodes in a radial-ish tree by type
            simulation.stop();

            const docs = graphData.nodes.filter(n => n.type === "document");
            const secs = graphData.nodes.filter(n => n.type === "section");
            const ents = graphData.nodes.filter(n => n.type === "entity");

            // Documents in center ring
            arrangeCircle(docs, width / 2, height / 2, Math.min(width, height) * 0.1);
            // Sections in middle ring
            arrangeCircle(secs, width / 2, height / 2, Math.min(width, height) * 0.25);
            // Entities in outer ring
            arrangeCircle(ents, width / 2, height / 2, Math.min(width, height) * 0.38);

            graphData.nodes.forEach(n => {
                n.fx = n.x;
                n.fy = n.y;
            });

            simulation.alpha(0.3).restart();

        } else {
            // Force layout: release all fixed positions
            graphData.nodes.forEach(n => {
                n.fx = null;
                n.fy = null;
            });
            simulation.alpha(0.8).restart();
        }
    }

    function arrangeCircle(nodes, cx, cy, radius) {
        nodes.forEach((n, i) => {
            const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
            n.x = cx + radius * Math.cos(angle);
            n.y = cy + radius * Math.sin(angle);
        });
    }

    // ---------------------------------------------------------------
    // Reset
    // ---------------------------------------------------------------
    function resetAll() {
        // Clear search
        searchInput.value = "";

        // Reset highlight
        resetHighlight();

        // Hide details
        hideDetails();

        // Reset zoom
        const width  = window.innerWidth;
        const height = window.innerHeight - 56;
        svg.transition().duration(500).call(
            svg.__zoom_behavior.transform,
            d3.zoomIdentity
        );

        // Reset layout to force
        if (currentLayout !== "force") {
            layoutToggle.value = "force";
            switchLayout("force");
        }
    }

    // ---------------------------------------------------------------
    // Resize
    // ---------------------------------------------------------------
    function onResize() {
        const width  = window.innerWidth;
        const height = window.innerHeight - 56;
        svg.attr("viewBox", [0, 0, width, height]);

        if (simulation) {
            simulation.force("center", d3.forceCenter(width / 2, height / 2));
            simulation.alpha(0.3).restart();
        }
    }

    // ---------------------------------------------------------------
    // Controls binding
    // ---------------------------------------------------------------
    function bindControls() {
        // Debounced search
        let searchTimer = null;
        searchInput.addEventListener("input", () => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => onSearch(searchInput.value), 200);
        });

        // Escape to clear search
        searchInput.addEventListener("keydown", (e) => {
            if (e.key === "Escape") {
                searchInput.value = "";
                resetHighlight();
                searchInput.blur();
            }
        });

        resetBtn.addEventListener("click", resetAll);

        layoutToggle.addEventListener("change", () => {
            switchLayout(layoutToggle.value);
        });

        detailsClose.addEventListener("click", () => {
            hideDetails();
            resetHighlight();
        });

        // Keyboard shortcut: / to focus search
        document.addEventListener("keydown", (e) => {
            if (e.key === "/" && document.activeElement !== searchInput) {
                e.preventDefault();
                searchInput.focus();
            }
        });

        // Query path visualization controls
        document.getElementById("query-btn").addEventListener("click", submitQuery);
        document.getElementById("query-input").addEventListener("keypress", (e) => {
            if (e.key === "Enter") submitQuery();
        });
        document.getElementById("clear-path-btn").addEventListener("click", clearTraversalOverlay);
        document.getElementById("replay-btn").addEventListener("click", () => {
            if (window._lastTraversalPath) replayTraversal(window._lastTraversalPath);
        });
    }

    // ---------------------------------------------------------------
    // Temporal Timeline Controls
    // ---------------------------------------------------------------

    function detectVersionedDocuments() {
        const groups = {};
        graphData.nodes.forEach(n => {
            if (n.type === "document" && n.doc_group) {
                if (!groups[n.doc_group]) groups[n.doc_group] = [];
                groups[n.doc_group].push(n.doc_version || 1);
            }
        });
        return groups;
    }

    function initTimelineControls() {
        const groups = detectVersionedDocuments();
        const groupNames = Object.keys(groups);
        if (groupNames.length === 0) return;  // no versioned docs, keep hidden

        const controls = document.getElementById("timeline-controls");
        const slider = document.getElementById("version-slider");
        const label = document.getElementById("version-label");
        const select = document.getElementById("doc-group-select");

        // Populate doc group dropdown
        groupNames.forEach(g => {
            const opt = document.createElement("option");
            opt.value = g;
            opt.textContent = g;
            select.appendChild(opt);
        });

        // Show controls
        controls.style.display = "flex";

        // On group change, update slider range
        select.addEventListener("change", () => {
            const group = select.value;
            if (!group || !groups[group]) {
                slider.max = 1;
                slider.value = 1;
                label.textContent = "v1";
                return;
            }
            const versions = groups[group].sort((a, b) => a - b);
            slider.min = versions[0];
            slider.max = versions[versions.length - 1];
            slider.value = versions[versions.length - 1];
            label.textContent = "v" + slider.value;
        });

        // On slider change, re-fetch versioned graph
        slider.addEventListener("input", async () => {
            label.textContent = "v" + slider.value;
            const group = select.value;
            if (!group) return;
            await fetchVersionedGraph(group, parseInt(slider.value));
        });
    }

    async function fetchVersionedGraph(docGroup, version) {
        try {
            const res = await fetch(`/api/graph?doc_group=${encodeURIComponent(docGroup)}&version=${version}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            applyTemporalStyles(data);
        } catch (err) {
            console.warn("Failed to fetch versioned graph:", err.message);
        }
    }

    function applyTemporalStyles(data) {
        // Build a map of entity label -> temporal_status
        const statusMap = {};
        data.nodes.forEach(n => {
            if (n.temporal_status) statusMap[n.label] = n.temporal_status;
        });

        // Apply CSS classes to entity nodes
        nodeSel.each(function(d) {
            const el = d3.select(this);
            // Remove any prior temporal classes
            el.classed("entity-appeared", false)
              .classed("entity-disappeared", false)
              .classed("entity-modified", false)
              .classed("entity-stable", false);

            if (d.type === "entity" && statusMap[d.label]) {
                const status = statusMap[d.label];
                if (status === "APPEARED") el.classed("entity-appeared", true);
                else if (status === "DISAPPEARED") el.classed("entity-disappeared", true);
                else if (status === "MODIFIED") el.classed("entity-modified", true);
                else if (status === "STABLE") el.classed("entity-stable", true);
            }
        });
    }

    // ---------------------------------------------------------------
    // Utilities
    // ---------------------------------------------------------------
    function truncate(str, max) {
        if (!str) return "";
        return str.length > max ? str.slice(0, max - 1) + "\u2026" : str;
    }

    function getEdgeColor(type) {
        switch (type) {
            case "parent_of":  return "#3fb950";
            case "contains":   return "#58a6ff";
            case "mentions":   return "#d29922";
            case "related_to": return "#bc8cff";
            default:           return "#6e7681";
        }
    }

    // ---------------------------------------------------------------
    // Query Path Visualization
    // ---------------------------------------------------------------

    function renderTraversalPath(traversalPath, graphQueries) {
        if (!traversalPath || traversalPath.length === 0) return;

        // Store for replay
        window._lastTraversalPath = traversalPath;

        // Dim all nodes and edges
        nodeSel.classed("dimmed", true);
        linkSel.classed("dimmed", true);

        // Build set of path node IDs
        const pathNodeIds = new Set();
        traversalPath.forEach(function (step) {
            var prefix = step.node_type === "entity" ? "ent_" :
                         step.node_type === "section" ? "sec_" : "doc_";
            pathNodeIds.add(prefix + step.node_id);
        });

        // Highlight path nodes
        nodeSel.each(function (d) {
            if (pathNodeIds.has(d.id)) {
                d3.select(this).classed("dimmed", false).classed("path-node", true);
            }
        });

        // Highlight edges between path nodes
        linkSel.each(function (d) {
            var srcId = typeof d.source === "object" ? d.source.id : d.source;
            var tgtId = typeof d.target === "object" ? d.target.id : d.target;
            if (pathNodeIds.has(srcId) && pathNodeIds.has(tgtId)) {
                d3.select(this).classed("dimmed", false).classed("path-edge", true);
            }
        });

        // Add step badges inside the zoom container
        var g = svg.__container;
        g.selectAll(".step-badge").remove();

        traversalPath.forEach(function (step) {
            var prefix = step.node_type === "entity" ? "ent_" :
                         step.node_type === "section" ? "sec_" : "doc_";
            var nodeId = prefix + step.node_id;

            nodeSel.each(function (d) {
                if (d.id === nodeId) {
                    g.append("circle")
                        .attr("class", "step-badge")
                        .attr("cx", d.x - 12)
                        .attr("cy", d.y - 12)
                        .attr("r", 8)
                        .attr("fill", "#238636");

                    g.append("text")
                        .attr("class", "step-badge")
                        .attr("x", d.x - 12)
                        .attr("y", d.y - 8)
                        .attr("text-anchor", "middle")
                        .attr("fill", "#fff")
                        .attr("font-size", "10px")
                        .attr("font-weight", "bold")
                        .text(step.step_number);
                }
            });
        });

        // Show traversal panel
        renderTraversalPanel(traversalPath, graphQueries);

        document.getElementById("clear-path-btn").style.display = "inline-block";
        document.getElementById("replay-btn").style.display = "inline-block";
    }

    function replayTraversal(traversalPath) {
        clearTraversalOverlay();

        // Dim everything
        nodeSel.classed("dimmed", true);
        linkSel.classed("dimmed", true);

        traversalPath.forEach(function (step, i) {
            setTimeout(function () {
                var prefix = step.node_type === "entity" ? "ent_" :
                             step.node_type === "section" ? "sec_" : "doc_";
                var nodeId = prefix + step.node_id;

                nodeSel.each(function (d) {
                    if (d.id === nodeId) {
                        d3.select(this)
                            .classed("dimmed", false)
                            .classed("path-node", true)
                            .select("circle")
                            .transition()
                            .duration(200)
                            .attr("r", function () { return +d3.select(this).attr("r") + 4; })
                            .transition()
                            .duration(200)
                            .attr("r", function () { return +d3.select(this).attr("r") - 4; });
                    }
                });

                // On last step, show panel and buttons again
                if (i === traversalPath.length - 1) {
                    renderTraversalPanel(traversalPath, []);
                    document.getElementById("clear-path-btn").style.display = "inline-block";
                    document.getElementById("replay-btn").style.display = "inline-block";
                }
            }, i * 400);
        });
    }

    function renderTraversalPanel(traversalPath, graphQueries) {
        var panel = document.getElementById("traversal-panel");
        var stepsDiv = document.getElementById("traversal-steps");
        var sqlDiv = document.getElementById("query-sql-list");

        // Render steps
        stepsDiv.innerHTML = traversalPath.map(function (step) {
            var borderColor = step.node_type === "entity" ? "#d29922" :
                              step.node_type === "section" ? "#3fb950" : "#58a6ff";
            var edgeInfo = step.edge_label
                ? '<span style="color:#8b949e; font-size:11px;"> ' +
                  (step.edge_direction === "reverse" ? "\u2190" : "\u2192") +
                  " " + step.edge_label + "</span>"
                : "";
            return '<div style="padding:6px 8px; margin:4px 0; background:#0d1117; border-radius:6px; border-left:3px solid ' + borderColor + ';">' +
                '<span style="color:#8b949e; font-size:11px;">' + step.step_number + ".</span> " +
                '<span style="color:#e6edf3; font-size:12px;">[' + step.node_type + "] " + step.node_label + "</span>" +
                edgeInfo +
                '<div style="color:#8b949e; font-size:11px; margin-top:2px;">' + (step.reason || "") + "</div>" +
                "</div>";
        }).join("");

        // Render SQL queries
        if (graphQueries && graphQueries.length > 0) {
            sqlDiv.innerHTML = graphQueries.map(function (gq) {
                var ms = typeof gq.execution_ms === "number" ? gq.execution_ms.toFixed(1) : "?";
                return '<div style="padding:8px; margin:4px 0; background:#0d1117; border-radius:6px;">' +
                    '<div style="color:#58a6ff; font-size:12px; margin-bottom:4px;">' + (gq.purpose || "") + "</div>" +
                    '<pre style="color:#8b949e; font-size:11px; margin:0; white-space:pre-wrap; word-break:break-all;">' + (gq.sql || "") + "</pre>" +
                    '<div style="color:#3fb950; font-size:11px; margin-top:4px;">' + (gq.rows_returned || 0) + " rows in " + ms + "ms</div>" +
                    "</div>";
            }).join("");
        } else {
            sqlDiv.innerHTML = '<div style="color:#8b949e; font-size:12px;">No graph queries recorded</div>';
        }

        panel.style.display = "block";
    }

    function clearTraversalOverlay() {
        nodeSel.classed("dimmed", false).classed("path-node", false);
        linkSel.classed("dimmed", false).classed("path-edge", false);
        if (svg.__container) {
            svg.__container.selectAll(".step-badge").remove();
        }
        document.getElementById("traversal-panel").style.display = "none";
        document.getElementById("clear-path-btn").style.display = "none";
        document.getElementById("replay-btn").style.display = "none";
        document.getElementById("query-answer").style.display = "none";
    }

    async function submitQuery() {
        var input = document.getElementById("query-input");
        var question = input.value.trim();
        if (!question) return;

        var btn = document.getElementById("query-btn");
        btn.textContent = "Thinking...";
        btn.disabled = true;

        try {
            var resp = await fetch("/api/query?q=" + encodeURIComponent(question));
            var data = await resp.json();

            // Show answer
            var answerDiv = document.getElementById("query-answer");
            answerDiv.textContent = data.answer || "No answer returned";
            answerDiv.style.display = "block";

            // Render traversal path
            if (data.traversal_path && data.traversal_path.length > 0) {
                renderTraversalPath(data.traversal_path, data.graph_queries || []);
            }
        } catch (err) {
            console.error("Query failed:", err);
        } finally {
            btn.textContent = "Query";
            btn.disabled = false;
        }
    }

    // ---------------------------------------------------------------
    // Start
    // ---------------------------------------------------------------
    init();

})();
