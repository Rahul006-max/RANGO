import { useEffect, useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  GitBranch,
  Layers,
  FileText,
} from "lucide-react";

function levelFromNode(node, depth, hasChildren) {
  if (depth === 0) return "root";
  if (hasChildren) return "section";
  return "page";
}

function collectExpandMap(node, depth = 0, acc = {}) {
  if (!node || typeof node !== "object") return acc;
  if (node.id) acc[node.id] = depth < 2;
  const children = Array.isArray(node.children) ? node.children : [];
  children.forEach((child) => collectExpandMap(child, depth + 1, acc));
  return acc;
}

function countNodes(node) {
  if (!node) return 0;
  const children = Array.isArray(node.children) ? node.children : [];
  return 1 + children.reduce((sum, child) => sum + countNodes(child), 0);
}

function countLeaves(node) {
  if (!node) return 0;
  const children = Array.isArray(node.children) ? node.children : [];
  if (!children.length) return 1;
  return children.reduce((sum, child) => sum + countLeaves(child), 0);
}

export default function TreeViewer({ collectionId, axiosAuth, onBack }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tree, setTree] = useState(null);
  const [expanded, setExpanded] = useState({});
  const [selectedId, setSelectedId] = useState(null);
  const [queryInput, setQueryInput] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");

  const fetchTree = async () => {
    if (!collectionId) return;
    setLoading(true);
    setError("");
    try {
      const api = await axiosAuth();
      const res = await api.get(`/page-index/tree/${collectionId}`);
      const nextTree = res.data?.tree || null;
      setTree(nextTree);
      const nextExpanded = collectExpandMap(nextTree);
      setExpanded(nextExpanded);
      setSelectedId(nextTree?.id || null);
    } catch (e) {
      setTree(null);
      setSelectedId(null);
      setError(e.response?.data?.detail || "Failed to load tree index.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTree();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collectionId]);

  const normalizedQuery = appliedQuery.trim().toLowerCase();

  const highlightText = (text, query) => {
    if (!text) return "";
    if (!query || !query.trim()) return text;
    const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const parts = text.split(new RegExp(`(${escaped})`, "gi"));
    return parts.map((part, idx) =>
      part.toLowerCase() === query.toLowerCase() ? (
        <mark key={idx} className="treeMark">
          {part}
        </mark>
      ) : (
        <span key={idx}>{part}</span>
      ),
    );
  };

  const nodeMatches = (node) => {
    if (!normalizedQuery) return true;
    const title = (node?.title || "").toLowerCase();
    const summary = (node?.summary || "").toLowerCase();
    const text = (node?.text || "").toLowerCase();
    return (
      title.includes(normalizedQuery) ||
      summary.includes(normalizedQuery) ||
      text.includes(normalizedQuery)
    );
  };

  const subtreeMatches = (node) => {
    if (nodeMatches(node)) return true;
    const children = Array.isArray(node?.children) ? node.children : [];
    return children.some((child) => subtreeMatches(child));
  };

  const countMatchedNodes = (node) => {
    if (!node) return 0;
    const children = Array.isArray(node.children) ? node.children : [];
    const self = nodeMatches(node) ? 1 : 0;
    return (
      self + children.reduce((sum, child) => sum + countMatchedNodes(child), 0)
    );
  };

  const matchedNodeCount = useMemo(
    () => countMatchedNodes(tree),
    [tree, normalizedQuery],
  );

  const applySearch = () => {
    setAppliedQuery(queryInput);
  };

  const clearSearch = () => {
    setQueryInput("");
    setAppliedQuery("");
  };

  const selectedInfo = useMemo(() => {
    if (!tree || !selectedId) return null;
    const stack = [{ node: tree, depth: 0 }];
    while (stack.length) {
      const current = stack.pop();
      if (current.node.id === selectedId) {
        const children = Array.isArray(current.node.children)
          ? current.node.children
          : [];
        return {
          node: current.node,
          depth: current.depth,
          childCount: children.length,
          level: levelFromNode(
            current.node,
            current.depth,
            children.length > 0,
          ),
        };
      }
      const children = Array.isArray(current.node.children)
        ? current.node.children
        : [];
      for (let i = children.length - 1; i >= 0; i -= 1) {
        stack.push({ node: children[i], depth: current.depth + 1 });
      }
    }
    return null;
  }, [tree, selectedId]);

  const expandAll = () => {
    if (!tree) return;
    const all = {};
    const walk = (node) => {
      if (!node) return;
      if (node.id) all[node.id] = true;
      const children = Array.isArray(node.children) ? node.children : [];
      children.forEach(walk);
    };
    walk(tree);
    setExpanded(all);
  };

  const collapseAll = () => {
    if (!tree) return;
    setExpanded(tree.id ? { [tree.id]: true } : {});
  };

  const renderNode = (node, depth = 0) => {
    if (!node) return null;
    if (!subtreeMatches(node)) return null;

    const children = Array.isArray(node.children) ? node.children : [];
    const hasChildren = children.length > 0;
    const isExpanded = expanded[node.id] ?? depth < 2;
    const level = levelFromNode(node, depth, hasChildren);
    const isSelected = selectedId === node.id;

    return (
      <div key={node.id || `${node.title}-${depth}`} className="treeFlowWrap">
        <div
          className={`treeFlowNode ${isSelected ? "selected" : ""}`}
          style={{ marginLeft: depth * 14 }}
        >
          <button
            className="treeFlowToggle"
            disabled={!hasChildren}
            onClick={() =>
              hasChildren &&
              node.id &&
              setExpanded((prev) => ({ ...prev, [node.id]: !prev[node.id] }))
            }
            aria-label={
              hasChildren
                ? isExpanded
                  ? "Collapse node"
                  : "Expand node"
                : "Leaf node"
            }
          >
            {hasChildren ? (
              isExpanded ? (
                <ChevronDown size={14} />
              ) : (
                <ChevronRight size={14} />
              )
            ) : (
              <span className="treeFlowDot" />
            )}
          </button>

          <button
            className="treeFlowCard"
            onClick={() => setSelectedId(node.id)}
          >
            <div className="treeFlowHead">
              <span className="treeFlowTitle">{node.title || "Untitled"}</span>
              <span className={`treeLevelBadge ${level}`}>{level}</span>
            </div>
            <div className="treeFlowMeta">
              <span>
                <GitBranch size={12} /> {children.length} child
                {children.length === 1 ? "" : "ren"}
              </span>
              <span>
                <Layers size={12} /> depth {depth}
              </span>
            </div>
          </button>
        </div>

        {hasChildren && isExpanded && (
          <div className="treeFlowChildren">
            {children.map((child) => renderNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="configPanel">
      <div className="claudeCard">
        <div className="claudeCardHead">Tree Structure Viewer</div>
        <div className="claudeCardBody">
          <div className="treeToolbar">
            <input
              className="claudeInput"
              placeholder="Search title / summary / page text..."
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && applySearch()}
              style={{ flex: 1, minWidth: 220 }}
            />
            <button
              className="btn primary"
              onClick={applySearch}
              disabled={loading}
            >
              Search
            </button>
            <button className="btn" onClick={clearSearch} disabled={loading}>
              Clear
            </button>
            <button className="btn" onClick={fetchTree} disabled={loading}>
              {loading ? "Loading..." : "Refresh"}
            </button>
            <button
              className="btn"
              onClick={expandAll}
              disabled={!tree || loading}
            >
              Expand all
            </button>
            <button
              className="btn"
              onClick={collapseAll}
              disabled={!tree || loading}
            >
              Collapse all
            </button>
            <button className="btn" onClick={onBack}>
              Back to Chat
            </button>
          </div>

          {tree && (
            <div className="mini" style={{ marginBottom: 10 }}>
              Nodes <b>{countNodes(tree)}</b> | Leaves{" "}
              <b>{countLeaves(tree)}</b>
              {normalizedQuery && (
                <>
                  {" "}
                  | Matches <b>{matchedNodeCount}</b>
                </>
              )}
            </div>
          )}

          {loading && (
            <div className="treeEmptyState">Loading tree structure...</div>
          )}
          {!loading && error && <div className="treeEmptyState">{error}</div>}
          {!loading && !error && !tree && (
            <div className="treeEmptyState">
              No tree found for this collection.
            </div>
          )}

          {!loading && !error && tree && (
            <div className="treeViewerGrid">
              <div className="treeFlowChart">{renderNode(tree, 0)}</div>

              <div className="treeDetailsPanel">
                {!selectedInfo ? (
                  <div className="mini">Select a node to view details.</div>
                ) : (
                  <>
                    <div className="treeDetailsTitle">
                      {selectedInfo.node.title || "Untitled"}
                    </div>
                    <div className="treeDetailsChips">
                      <span className={`treeLevelBadge ${selectedInfo.level}`}>
                        {selectedInfo.level}
                      </span>
                      <span className="treeChip">
                        {selectedInfo.childCount} child
                        {selectedInfo.childCount === 1 ? "" : "ren"}
                      </span>
                      <span className="treeChip">
                        depth {selectedInfo.depth}
                      </span>
                    </div>

                    <div className="treeDetailsBlock">
                      <div className="treeDetailsLabel">Summary</div>
                      <div className="treeDetailsText">
                        {selectedInfo.node.summary
                          ? highlightText(
                              selectedInfo.node.summary,
                              normalizedQuery,
                            )
                          : "No summary available."}
                      </div>
                    </div>

                    {selectedInfo.childCount === 0 && (
                      <div className="treeDetailsBlock">
                        <div className="treeDetailsLabel">
                          <FileText size={13} style={{ marginRight: 6 }} /> Page
                          Text
                        </div>
                        <div className="treeLeafFullText">
                          {selectedInfo.node.text
                            ? highlightText(
                                selectedInfo.node.text,
                                normalizedQuery,
                              )
                            : "No page text."}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
