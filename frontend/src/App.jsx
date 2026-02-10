import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import "./ModernApp.css";

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
} from "chart.js";
import { Bar } from "react-chartjs-2";

import { supabase } from "./supabaseClient";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

const API = "http://127.0.0.1:8000";

// ✅ Pipeline labeling (A/B/C/D instead of long names)
const PIPE_LABELS = ["A", "B", "C", "D", "CUSTOM"];
const labelForIndex = (idx) => PIPE_LABELS[idx] || `P${idx + 1}`;

export default function App() {
  // ✅ AUTH
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [error, setError] = useState("");

  // ✅ MODE
  const [mode, setMode] = useState("chat"); // chat | fast | compare

  // ✅ COLLECTIONS
  const [collectionId, setCollectionId] = useState("");
  const [collections, setCollections] = useState([]);

  // ✅ UPLOAD
  const [files, setFiles] = useState([]);
  const [uploadRes, setUploadRes] = useState(null);
  const [uploading, setUploading] = useState(false);

  // ✅ ASK / CHAT
  const [question, setQuestion] = useState("");
  const [askRes, setAskRes] = useState(null);
  const [asking, setAsking] = useState(false);

  // ✅ CHAT
  const [chatMessages, setChatMessages] = useState([]);
  const [chatLoading, setChatLoading] = useState(false);

  // ✅ FILES + PDF VIEWER
  const [collectionFiles, setCollectionFiles] = useState([]);
  const [activePdfUrl, setActivePdfUrl] = useState("");
  const [activePdfName, setActivePdfName] = useState("");
  const [showPdfViewer, setShowPdfViewer] = useState(false);

  // ✅ DASHBOARD
  const [showDashboard, setShowDashboard] = useState(true);

  // ✅ LEADERBOARD
  const [leaderboard, setLeaderboard] = useState(null);
  const [leaderboardLoading, setLeaderboardLoading] = useState(false);
  const [leaderboardMode, setLeaderboardMode] = useState("all");
  const [leaderboardRange, setLeaderboardRange] = useState("30d");

  // ✅ Report download
  const [downloadingReport, setDownloadingReport] = useState(false);

  // ✅ CUSTOM USER PIPELINE (+1 optional, doesn't replace 4 system pipelines)
  const [customEnabled, setCustomEnabled] = useState(false);
  const [customConfig, setCustomConfig] = useState({
    preset_name: "Custom",
    chunk_size: 800,
    overlap: 120,
    top_k: 6,
    search_type: "mmr",
  });
  const [customDirty, setCustomDirty] = useState(false);
  const [customSaving, setCustomSaving] = useState(false);
  const [indexMissing, setIndexMissing] = useState(false);
  const [rebuildingIndex, setRebuildingIndex] = useState(false);

  // ✅ CHUNK EXPLORER (DEBUG TOOL)
  const [chunkExplorerOpen, setChunkExplorerOpen] = useState(false);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [chunks, setChunks] = useState([]);
  const [chunksTotal, setChunksTotal] = useState(0);
  const [chunkQuery, setChunkQuery] = useState("");
  const [chunkLimit, setChunkLimit] = useState(20);
  const [chunkOffset, setChunkOffset] = useState(0);
  const [chunkFilterPipeline, setChunkFilterPipeline] = useState("");
  const [chunkFilterFileId, setChunkFilterFileId] = useState("");
  const [chunkFilterPage, setChunkFilterPage] = useState("");

  // ✅ BATCH EVALUATION (TEST SET)
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchDatasetText, setBatchDatasetText] = useState("");
  const [batchItems, setBatchItems] = useState([]);
  const [batchMode, setBatchMode] = useState("fast");
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchRunId, setBatchRunId] = useState("");
  const [batchProgress, setBatchProgress] = useState(null);
  const [batchPollingInterval, setBatchPollingInterval] = useState(null);

  // ✅ IMAGE TEST MODE (RAG VISION ACCURACY)
  const [imgFile, setImgFile] = useState(null);
  const [imgPreview, setImgPreview] = useState("");
  const [imgQuestion, setImgQuestion] = useState("");
  const [imgLoading, setImgLoading] = useState(false);
  const [imgRes, setImgRes] = useState(null);
  const [showImgAdvanced, setShowImgAdvanced] = useState(false);

  // --------------------------------
  // Axios Auth
  // --------------------------------
  const axiosAuth = async () => {
    const { data, error } = await supabase.auth.getSession();
    const token = data?.session?.access_token;

    if (error) throw new Error(error.message);
    if (!data?.session) throw new Error("No active session. Please login.");
    if (!token) throw new Error("No token found. Please login.");

    const instance = axios.create({ baseURL: API });

    instance.interceptors.request.use((config) => {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
      return config;
    });

    return instance;
  };

  // --------------------------------
  // Auth UI helpers
  // --------------------------------
  const signInWithGoogle = async () => {
    setError("");
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
    });
    if (error) setError(error.message);
  };

  const signOut = async () => {
    await supabase.auth.signOut();
    setUser(null);

    // reset app state
    setCollections([]);
    setCollectionId("");
    setFiles([]);
    setUploadRes(null);
    setQuestion("");
    setAskRes(null);
    setChatMessages([]);
    setActivePdfUrl("");
    setActivePdfName("");
    setCollectionFiles([]);
    setLeaderboard(null);
    setShowDashboard(false);
    setShowPdfViewer(false);
    setMode("chat");
  };

  // --------------------------------
  // API: Collections
  // --------------------------------
  const fetchCollections = async () => {
    try {
      const api = await axiosAuth();
      const res = await api.get(`/collections`);
      setCollections(res.data.collections || []);
    } catch (err) {
      console.log("fetchCollections error", err);
    }
  };

  const renameCollection = async () => {
    if (!collectionId) return setError("Select a collection first.");
    const newName = window.prompt("Enter new collection name:");
    if (!newName?.trim()) return;

    setError("");
    try {
      const api = await axiosAuth();
      await api.post(`/collections/${collectionId}/rename`, {
        name: newName.trim(),
      });
      await fetchCollections();
      alert("Renamed ✅");
    } catch (err) {
      console.log(err);
      setError("Rename failed.");
    }
  };

  const deleteCollection = async () => {
    if (!collectionId) return setError("Select a collection first.");
    const ok = window.confirm(
      `Delete collection?\n\nThis deletes DB rows + local chroma.\n\nID: ${collectionId}`,
    );
    if (!ok) return;

    try {
      const api = await axiosAuth();
      await api.delete(`/collections/${collectionId}`);
      await fetchCollections();

      setCollectionId("");
      setAskRes(null);
      setUploadRes(null);
      setChatMessages([]);
      setCollectionFiles([]);
      setActivePdfUrl("");
      setActivePdfName("");
      setLeaderboard(null);
      setShowDashboard(false);
      setShowPdfViewer(false);

      alert("Deleted ✅");
    } catch (err) {
      console.log(err);
      setError("Delete failed.");
    }
  };

  // --------------------------------
  // API: Upload
  // --------------------------------
  const uploadMultiPDF = async () => {
    if (!files.length) return setError("Select at least 1 PDF.");
    if (!user) return setError("Login first.");

    setUploading(true);
    setError("");
    setUploadRes(null);
    setAskRes(null);
    setShowDashboard(false);

    try {
      const api = await axiosAuth();
      const formData = new FormData();
      files.forEach((f) => formData.append("files", f));
      if (collectionId) formData.append("collection_id", collectionId);

      const res = await api.post(`/upload-multi`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      setUploadRes(res.data);
      setCollectionId(res.data.collection_id);

      await fetchCollections();
      setTimeout(() => {
        fetchCollectionFiles();
        fetchLeaderboard();
        fetchChat();
      }, 350);
    } catch (err) {
      console.log(err);
      setError("Upload failed. Check backend + auth.");
    } finally {
      setUploading(false);
    }
  };

  // --------------------------------
  // API: Files + PDF Viewer
  // --------------------------------
  const fetchCollectionFiles = async () => {
    if (!collectionId) return;

    try {
      const api = await axiosAuth();
      const res = await api.get(`/collections/${collectionId}/files`);
      setCollectionFiles(res.data.files || []);
    } catch (err) {
      console.log("files fetch error", err);
      setCollectionFiles([]);
    }
  };

  const openPdfInViewer = async ({ fileId, page = null } = {}) => {
    try {
      if (!collectionId) return;

      if (!collectionFiles.length) {
        setError("No PDFs found in this collection.");
        return;
      }

      const targetFile = fileId
        ? collectionFiles.find((f) => f.id === fileId)
        : collectionFiles[0];

      if (!targetFile) {
        setError("File not found.");
        return;
      }

      const api = await axiosAuth();
      const res = await api.get(
        `/collections/${collectionId}/files/${targetFile.id}/signed-url`,
      );

      const signedUrl = res.data?.signed_url;
      const filename = res.data?.filename || targetFile.filename || "PDF";

      if (!signedUrl) {
        setError("Signed URL not received.");
        return;
      }

      const finalUrl =
        page !== null && page !== undefined && page !== ""
          ? `${signedUrl}#page=${Number(page) + 1}`
          : signedUrl;

      setActivePdfUrl(finalUrl);
      setActivePdfName(filename);
      setShowPdfViewer(true);
    } catch (err) {
      console.log(err);
      setError("Could not open PDF viewer.");
    }
  };

  // --------------------------------
  // API: Chat
  // --------------------------------
  const fetchChat = async () => {
    if (!collectionId) return;
    try {
      const api = await axiosAuth();
      const res = await api.get(`/collections/${collectionId}/chat`);
      setChatMessages(res.data.messages || []);
    } catch (err) {
      console.log("chat fetch error", err);
      setChatMessages([]);
    }
  };

  const clearChat = async () => {
    if (!collectionId) return setError("Select a collection first.");
    const ok = window.confirm("Clear chat for this collection?");
    if (!ok) return;

    try {
      const api = await axiosAuth();
      await api.delete(`/collections/${collectionId}/chat`);
      setChatMessages([]);
      setAskRes(null);
      setShowDashboard(false);
      alert("Chat cleared ✅");
    } catch (err) {
      console.log(err);
      setError("Clear chat failed.");
    }
  };

  const sendChatMessage = async () => {
    setError("");
    setChatLoading(true);

    const userMsg = question.trim();
    if (!userMsg) {
      setChatLoading(false);
      return;
    }

    setChatMessages((prev) => [
      ...prev,
      { role: "user", message: userMsg, created_at: new Date().toISOString() },
      { role: "assistant", message: "", created_at: new Date().toISOString() },
    ]);

    setQuestion("");

    try {
      const { data } = await supabase.auth.getSession();
      const token = data?.session?.access_token;

      const res = await fetch(`${API}/chat-stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          question: userMsg,
          collection_id: collectionId,
        }),
      });

      if (!res.ok) throw new Error("Streaming failed.");

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let assistantText = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        assistantText += chunk;

        setChatMessages((prev) => {
          const updated = [...prev];
          for (let i = updated.length - 1; i >= 0; i--) {
            if (updated[i].role === "assistant") {
              updated[i] = { ...updated[i], message: assistantText };
              break;
            }
          }
          return updated;
        });
      }

      fetchLeaderboard();
      fetchChat();
    } catch (err) {
      console.log(err);
      setError("Chat failed.");
      setChatMessages((prev) => prev.slice(0, -2));
    } finally {
      setChatLoading(false);
    }
  };

  // --------------------------------
  // API: Ask (fast/compare)
  // --------------------------------
  const askQuestion = async () => {
    if (!question.trim()) return setError("Enter a question.");
    if (!collectionId) return setError("Select a collection first.");
    if (mode === "chat")
      return setError("Chat mode uses streaming endpoint, not /ask");

    setAsking(true);
    setError("");
    setAskRes(null);
    setShowDashboard(false);

    try {
      const api = await axiosAuth();

      const payload = {
        question: question.trim(),
        collection_id: collectionId,
        mode,
        custom_pipeline: {
          enabled: customEnabled,
          preset_name: "Custom",
          chunk_size: Number(customConfig.chunk_size) || 800,
          overlap: Number(customConfig.overlap) || 120,
          top_k: Number(customConfig.top_k) || 6,
          search_type: customConfig.search_type || "mmr",
        },
      };

      console.log("Sending /ask payload:", payload);

      const res = await api.post("/ask", payload);

      setAskRes(res.data);
      setShowDashboard(true); // ✅ auto open after ask
      setIndexMissing(false); // Reset on success
    } catch (err) {
      console.log("Ask error:", err);
      console.log("Error response:", err.response);
      console.log("Error response data:", err.response?.data);
      console.log("Error detail:", err.response?.data?.detail);

      const errorDetail = err.response?.data?.detail;

      // ✅ Handle structured error for missing local index
      if (
        typeof errorDetail === "object" &&
        errorDetail.error === "index_missing_locally"
      ) {
        setError("⚠️ Collection exists but local index is missing.");
        setIndexMissing(true);
      } else if (errorDetail === "Invalid collection_id. Upload first.") {
        setError("⚠️ No PDFs in this collection. Please upload PDFs first.");
        setIndexMissing(false);
      } else if (errorDetail) {
        setError("Ask failed: " + JSON.stringify(errorDetail));
        setIndexMissing(false);
      } else if (err.response?.data) {
        setError("Ask failed: " + JSON.stringify(err.response.data));
        setIndexMissing(false);
      } else {
        setError("Ask failed. Check backend logs.");
        setIndexMissing(false);
      }
    } finally {
      setAsking(false);
    }
  };

  // --------------------------------
  // Rebuild Index
  // --------------------------------
  const rebuildIndex = async () => {
    if (!collectionId) return;

    setRebuildingIndex(true);
    setError("");
    try {
      const api = await axiosAuth();
      const res = await api.post(`/collections/${collectionId}/rebuild-index`);

      let successMsg = `✅ Index rebuilt successfully! ${res.data.chunks_created} chunks in ${res.data.time_taken_sec}s`;
      if (res.data.failed_files && res.data.failed_files.length > 0) {
        successMsg += ` (⚠️ ${res.data.failed_files.length} files failed)`;
      }

      setError(successMsg);
      setIndexMissing(false);
    } catch (err) {
      console.log("❌ Rebuild error:", err);
      console.log("❌ Rebuild error response:", err.response);

      const errorDetail =
        err.response?.data?.detail || err.message || "Unknown error";
      setError(`Failed to rebuild index: ${errorDetail}`);
    } finally {
      setRebuildingIndex(false);
    }
  };

  const handleUnifiedQuery = async () => {
    if (!user) return setError("Login first.");
    if (!collectionId) return setError("Upload/select a collection first.");
    if (!question.trim()) return setError("Enter a question.");

    if (mode === "chat") await sendChatMessage();
    else await askQuestion();
  };

  // --------------------------------
  // Leaderboard
  // --------------------------------
  const fetchLeaderboard = async () => {
    if (!collectionId) return;

    setLeaderboardLoading(true);
    try {
      const api = await axiosAuth();
      const res = await api.get(`/collections/${collectionId}/leaderboard`, {
        params: {
          mode: leaderboardMode,
          range: leaderboardRange,
        },
      });
      setLeaderboard(res.data);
    } catch (err) {
      console.log("leaderboard fetch error", err);
      setLeaderboard(null);
    } finally {
      setLeaderboardLoading(false);
    }
  };

  // --------------------------------
  // Chunk Explorer
  // --------------------------------
  const fetchChunks = async () => {
    if (!collectionId) return;
    setChunksLoading(true);
    setError("");

    try {
      const api = await axiosAuth();
      const params = {
        q: chunkQuery || undefined,
        pipeline: chunkFilterPipeline || undefined,
        file_id: chunkFilterFileId || undefined,
        page: chunkFilterPage || undefined,
        limit: chunkLimit,
        offset: chunkOffset,
      };

      const res = await api.get(`/collections/${collectionId}/chunks`, {
        params,
      });
      setChunks(res.data.chunks || []);
      setChunksTotal(res.data.total || 0);
    } catch (e) {
      console.log("Chunk fetch error:", e);
      setChunks([]);
      setChunksTotal(0);
      setError("Failed to load chunks.");
    } finally {
      setChunksLoading(false);
    }
  };

  // Auto-fetch chunks when offset changes
  useEffect(() => {
    if (chunkExplorerOpen && collectionId) {
      fetchChunks();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chunkOffset]);

  // --------------------------------
  // Batch Evaluation
  // --------------------------------
  const parseBatchDataset = () => {
    try {
      const parsed = JSON.parse(batchDatasetText);
      if (parsed.items && Array.isArray(parsed.items)) {
        setBatchItems(parsed.items);
        setError("");
      } else if (Array.isArray(parsed)) {
        setBatchItems(parsed);
        setError("");
      } else {
        setError("Invalid JSON format. Expected {items: [...]} or [...]");
      }
    } catch (e) {
      setError("Failed to parse JSON: " + e.message);
    }
  };

  const runBatchEval = async () => {
    if (!collectionId) return setError("Select a collection first.");
    if (!batchItems.length) return setError("Add at least 1 question.");

    setBatchRunning(true);
    setError("");

    try {
      const api = await axiosAuth();
      const res = await api.post(`/collections/${collectionId}/batch-eval`, {
        mode: batchMode,
        items: batchItems,
      });

      setBatchRunId(res.data.run_id);
      startBatchPolling(res.data.run_id);
    } catch (e) {
      console.log("Batch eval error:", e);
      setError(
        "Batch eval failed: " + (e.response?.data?.detail || "Unknown error"),
      );
      setBatchRunning(false);
    }
  };

  const startBatchPolling = (runId) => {
    const interval = setInterval(async () => {
      try {
        const api = await axiosAuth();
        const res = await api.get(`/batch-eval/${runId}`);
        setBatchProgress(res.data);

        if (res.data.status === "done") {
          clearInterval(interval);
          setBatchRunning(false);
        }
      } catch (e) {
        console.log("Polling error:", e);
        clearInterval(interval);
        setBatchRunning(false);
      }
    }, 1200);

    setBatchPollingInterval(interval);
  };

  const stopBatchPolling = () => {
    if (batchPollingInterval) {
      clearInterval(batchPollingInterval);
      setBatchPollingInterval(null);
    }
  };

  const downloadBatchReport = () => {
    if (!batchProgress) return;
    const content = JSON.stringify(batchProgress, null, 2);
    downloadBlob(content, `batch-eval-${batchRunId}.json`, "application/json");
  };

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (batchPollingInterval) {
        clearInterval(batchPollingInterval);
      }
    };
  }, [batchPollingInterval]);

  // --------------------------------
  // Report Download Helpers
  // --------------------------------
  const downloadBlob = (content, filename, mimeType) => {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const safeFileName = (name) => (name || "").replace(/[^a-z0-9_-]/gi, "_");

  const buildBaseReportData = () => {
    return {
      generated_at: new Date().toISOString(),
      collection_id: collectionId,
      collection_name: activeCollectionName,
      mode,
      question: askRes?.question || question,
      best_pipeline: askRes?.best_pipeline,
      final_answer: askRes?.final_answer,
      metrics: askRes?.metrics || null,
      citations: askRes?.citations || [],
      pipelines: askRes?.retrieval_comparison || [],
    };
  };

  // --------------------------------
  // Export TXT
  // --------------------------------
  const downloadReportTXT = async () => {
    if (!askRes?.retrieval_comparison || mode === "chat") {
      setError("No compare data available. Use Fast/Compare mode first.");
      return;
    }

    setDownloadingReport(true);
    try {
      const data = buildBaseReportData();

      const txt = `RAG PIPELINE REPORT
===================

Collection: ${data.collection_id}
Collection Name: ${data.collection_name}
Mode: ${data.mode}
Best Pipeline: ${data.best_pipeline}
Generated: ${new Date(data.generated_at).toLocaleString()}

QUESTION
--------
${data.question}

ANSWER
------
${data.final_answer}

PIPELINES
---------
${(data.pipelines || [])
  .map((p, i) => {
    return `\n${i + 1}) ${p.pipeline}\n- Final Score: ${p.scores?.final ?? 0}\n- Relevance: ${p.scores?.relevance ?? 0}\n- Grounded: ${p.scores?.grounded ?? 0}\n- Quality: ${p.scores?.quality ?? 0}\n- Efficiency: ${p.scores?.efficiency ?? 0}\n- Chunk: ${p.chunk_size} | Overlap: ${p.overlap}\n- Search: ${p.search_type} | Top-K: ${p.top_k}\n- Retrieval Time: ${p.retrieval_time_sec}s\n`;
  })
  .join("\n")}

CITATIONS
---------
${(data.citations || []).length ? data.citations.map((c, idx) => `${idx + 1}. ${c.source} (page ${c.page})`).join("\n") : "No citations"}
`;

      const fname = `RAG_Report_${safeFileName(collectionId?.slice(0, 8))}_${Date.now()}.txt`;
      downloadBlob(txt, fname, "text/plain");
    } catch {
      setError("TXT report download failed.");
    } finally {
      setDownloadingReport(false);
    }
  };

  // --------------------------------
  // Export JSON
  // --------------------------------
  const downloadReportJSON = () => {
    if (!askRes?.retrieval_comparison || mode === "chat") {
      setError("No comparison data available. Use Fast/Compare mode first.");
      return;
    }

    const data = buildBaseReportData();
    const jsonText = JSON.stringify(data, null, 2);
    const fname = `RAG_Report_${safeFileName(collectionId?.slice(0, 8))}_${Date.now()}.json`;
    downloadBlob(jsonText, fname, "application/json");
  };

  // --------------------------------
  // Export CSV
  // --------------------------------
  const downloadReportCSV = () => {
    if (!askRes?.retrieval_comparison || mode === "chat") {
      setError("No comparison data available. Use Fast/Compare mode first.");
      return;
    }

    const data = buildBaseReportData();

    const header = [
      "pipeline",
      "final_score",
      "relevance",
      "grounded",
      "quality",
      "efficiency",
      "retrieval_time_sec",
      "chunk_size",
      "overlap",
      "top_k",
      "search_type",
    ];

    const rows = (data.pipelines || []).map((p) => [
      p.pipeline,
      p.scores?.final ?? 0,
      p.scores?.relevance ?? 0,
      p.scores?.grounded ?? 0,
      p.scores?.quality ?? 0,
      p.scores?.efficiency ?? 0,
      p.retrieval_time_sec ?? "",
      p.chunk_size ?? "",
      p.overlap ?? "",
      p.top_k ?? "",
      p.search_type ?? "",
    ]);

    const escapeCSV = (val) => {
      const s = String(val ?? "");
      if (s.includes(",") || s.includes("\n") || s.includes('"')) {
        return `"${s.replaceAll('"', '""')}"`;
      }
      return s;
    };

    const csvText = [
      header.join(","),
      ...rows.map((r) => r.map(escapeCSV).join(",")),
    ].join("\n");
    const fname = `RAG_Pipelines_${safeFileName(collectionId?.slice(0, 8))}_${Date.now()}.csv`;
    downloadBlob(csvText, fname, "text/csv");
  };

  // --------------------------------
  // Charts
  // --------------------------------
  const pipelineData = askRes?.retrieval_comparison || [];

  const labels = useMemo(
    () => pipelineData.map((p) => p.pipeline),
    [pipelineData],
  );
  const retrievalTimes = useMemo(
    () => pipelineData.map((p) => p.retrieval_time_sec),
    [pipelineData],
  );
  const relevanceScores = useMemo(
    () => pipelineData.map((p) => p.scores?.relevance ?? 0),
    [pipelineData],
  );
  const groundedScores = useMemo(
    () => pipelineData.map((p) => p.scores?.grounded ?? 0),
    [pipelineData],
  );
  const qualityScores = useMemo(
    () => pipelineData.map((p) => p.scores?.quality ?? 0),
    [pipelineData],
  );
  const efficiencyScores = useMemo(
    () => pipelineData.map((p) => p.scores?.efficiency ?? 0),
    [pipelineData],
  );
  const finalScores = useMemo(
    () => pipelineData.map((p) => p.scores?.final ?? 0),
    [pipelineData],
  );

  const retrievalChart = {
    labels,
    datasets: [
      {
        label: "Retrieval Time (sec)",
        data: retrievalTimes,
        borderWidth: 3,
        borderColor: "#000",
      },
    ],
  };

  const scoreChart = {
    labels,
    datasets: [
      {
        label: "Relevance (0-10)",
        data: relevanceScores,
        borderWidth: 3,
        borderColor: "#000",
      },
      {
        label: "Grounded (0-10)",
        data: groundedScores,
        borderWidth: 3,
        borderColor: "#000",
      },
    ],
  };

  const qualityEfficiencyChart = {
    labels,
    datasets: [
      {
        label: "Quality (0-10)",
        data: qualityScores,
        borderWidth: 3,
        borderColor: "#000",
      },
      {
        label: "Efficiency (0-10)",
        data: efficiencyScores,
        borderWidth: 3,
        borderColor: "#000",
      },
    ],
  };

  const finalScoreChart = {
    labels,
    datasets: [
      {
        label: "Final Score (0-10)",
        data: finalScores,
        borderWidth: 3,
        borderColor: "#000",
      },
    ],
  };

  // Brutalist chart options
  const brutalistChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: {
        display: true,
        labels: {
          color: "#000",
          font: { weight: "900", size: 12 },
          boxWidth: 14,
          boxHeight: 14,
          padding: 12,
        },
      },
      tooltip: {
        enabled: true,
        backgroundColor: "#fff",
        titleColor: "#000",
        bodyColor: "#000",
        borderColor: "#000",
        borderWidth: 3,
        titleFont: { weight: "900", size: 12 },
        bodyFont: { weight: "800", size: 12 },
        padding: 12,
        cornerRadius: 0,
        displayColors: true,
        boxPadding: 6,
        callbacks: {
          label: (ctx) => {
            const v = ctx.parsed?.y ?? ctx.raw;
            return `${ctx.dataset.label}: ${v}`;
          },
        },
      },
    },
    scales: {
      x: {
        ticks: {
          color: "#000",
          font: { weight: "900", size: 11 },
        },
        grid: {
          color: "#000",
          lineWidth: 2,
        },
        border: {
          color: "#000",
          width: 3,
        },
      },
      y: {
        beginAtZero: true,
        ticks: {
          color: "#000",
          font: { weight: "900", size: 11 },
        },
        grid: {
          color: "#000",
          lineWidth: 2,
        },
        border: {
          color: "#000",
          width: 3,
        },
      },
    },
  };

  // Brutalist color palette
  const brutalistColors = [
    "#000000", // black
    "#FFFBCC", // yellow
    "#FFE1E1", // pink
    "#E0E0E0", // gray
  ];

  // --------------------------------
  // Metrics Helpers
  // --------------------------------
  const fmtMs = (ms) => {
    if (ms === null || ms === undefined || Number.isNaN(ms)) return "N/A";
    return `${Math.round(ms)} ms`;
  };

  const fmtNum = (n) => {
    if (n === null || n === undefined || Number.isNaN(n)) return "N/A";
    return String(n);
  };

  const fmtMoney = (usd) => {
    if (usd === null || usd === undefined || Number.isNaN(usd)) return "N/A";
    return `$${Number(usd).toFixed(4)}`;
  };

  const safeMetrics = askRes?.metrics || {};

  // --------------------------------
  // Latency Chart
  // --------------------------------
  const timings = safeMetrics?.timings_ms || {};
  const latencyLabels = ["Embedding", "Retrieval", "Rerank", "LLM", "Total"];
  const latencyValues = [
    timings.embedding_ms ?? null,
    timings.retrieval_ms ?? null,
    timings.rerank_ms ?? null,
    timings.llm_ms ?? null,
    timings.total_ms ?? null,
  ].map((v) => (v === null ? 0 : v));

  const latencyChart = {
    labels: latencyLabels,
    datasets: [
      {
        label: "Latency (ms)",
        data: latencyValues,
        borderColor: "#000",
        borderWidth: 3,
        backgroundColor: brutalistColors[1],
      },
    ],
  };

  // Update chart datasets with brutalist styling
  retrievalChart.datasets[0].backgroundColor = brutalistColors[0];
  retrievalChart.datasets[0].borderColor = brutalistColors[0];
  retrievalChart.datasets[0].borderWidth = 3;

  scoreChart.datasets[0].backgroundColor = brutalistColors[0];
  scoreChart.datasets[0].borderColor = brutalistColors[0];
  scoreChart.datasets[0].borderWidth = 3;
  scoreChart.datasets[1].backgroundColor = brutalistColors[1];
  scoreChart.datasets[1].borderColor = "black";
  scoreChart.datasets[1].borderWidth = 3;

  qualityEfficiencyChart.datasets[0].backgroundColor = brutalistColors[2];
  qualityEfficiencyChart.datasets[0].borderColor = "black";
  qualityEfficiencyChart.datasets[0].borderWidth = 3;
  qualityEfficiencyChart.datasets[1].backgroundColor = brutalistColors[3];
  qualityEfficiencyChart.datasets[1].borderColor = "black";
  qualityEfficiencyChart.datasets[1].borderWidth = 3;

  finalScoreChart.datasets[0].backgroundColor = brutalistColors[0];
  finalScoreChart.datasets[0].borderColor = brutalistColors[0];
  finalScoreChart.datasets[0].borderWidth = 3;

  // --------------------------------
  // Helpers
  // --------------------------------
  const brutalCard = (title, body) => (
    <div className="b-card">
      <div className="b-head">{title}</div>
      <div className="b-body">{body}</div>
    </div>
  );

  const activeCollectionName = useMemo(() => {
    const found = collections.find((c) => c.id === collectionId);
    return found?.name || "—";
  }, [collections, collectionId]);

  // --------------------------------
  // Pipeline Config Functions
  // --------------------------------
  // Custom Pipeline Config (API)
  // --------------------------------
  const fetchCustomPipeline = async () => {
    if (!collectionId) return;
    try {
      const api = await axiosAuth();
      const res = await api.get(`/collections/${collectionId}/custom-pipeline`);
      const cfg = res.data?.custom_pipeline;
      if (cfg) {
        setCustomEnabled(!!cfg.enabled);
        setCustomConfig({
          preset_name: cfg.preset_name || "Custom",
          chunk_size: cfg.chunk_size ?? 800,
          overlap: cfg.overlap ?? 120,
          top_k: cfg.top_k ?? 6,
          search_type: cfg.search_type || "mmr",
        });
        setCustomDirty(false);
      }
    } catch {
      // Keep defaults
      console.log("No saved custom pipeline, using defaults");
    }
  };

  const saveCustomPipeline = async () => {
    if (!collectionId) return setError("Select a collection first.");
    setCustomSaving(true);
    setError("");
    try {
      const api = await axiosAuth();
      await api.post(`/collections/${collectionId}/custom-pipeline`, {
        enabled: customEnabled,
        ...customConfig,
      });
      setCustomDirty(false);
      alert("Custom pipeline saved ✅");
    } catch {
      setError("Failed to save custom pipeline.");
    } finally {
      setCustomSaving(false);
    }
  };

  const applyRecommended = () => {
    setCustomConfig({
      preset_name: "Custom",
      chunk_size: 900,
      overlap: 150,
      top_k: 8,
      search_type: "mmr",
    });
    setCustomDirty(true);
  };

  const updateCustomField = (field, value) => {
    setCustomConfig((prev) => ({ ...prev, [field]: value }));
    setCustomDirty(true);
  };

  // --------------------------------
  // Init
  // --------------------------------
  useEffect(() => {
    const init = async () => {
      setAuthLoading(true);
      const { data } = await supabase.auth.getSession();
      setUser(data?.session?.user ?? null);

      supabase.auth.onAuthStateChange((_event, session) => {
        setUser(session?.user ?? null);
      });

      setAuthLoading(false);
    };
    init();
  }, []);

  useEffect(() => {
    if (user?.id) fetchCollections();
  }, [user?.id]);

  useEffect(() => {
    if (collectionId) {
      fetchCollectionFiles();
      fetchLeaderboard();
      fetchChat();
      fetchCustomPipeline();
    }
  }, [collectionId]);

  // ✅ Refetch leaderboard when filters change
  useEffect(() => {
    if (collectionId) {
      fetchLeaderboard();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leaderboardMode, leaderboardRange]);

  // --------------------------------
  // UI Pieces
  // --------------------------------
  const ProfileAuthCard = () =>
    brutalCard(
      "PROFILE",
      authLoading ? (
        <div className="mini">Loading session...</div>
      ) : user ? (
        <div className="stack">
          <div className="pill">
            <div className="pillLabel">SIGNED IN AS</div>
            <div className="pillValue">{user.email}</div>
          </div>
          <button className="btn danger" onClick={signOut}>
            SIGN OUT
          </button>
        </div>
      ) : (
        <div className="stack">
          <div className="mini">You are not logged in.</div>
          <button className="btn activeBtn" onClick={signInWithGoogle}>
            SIGN IN WITH GOOGLE
          </button>
        </div>
      ),
    );

  const CustomPipelineCard = () =>
    brutalCard(
      "CUSTOM USER PIPELINE (+1 OPTIONAL)",
      <div className="stack">
        <div className="pill">
          <div className="pillLabel">STATUS</div>
          <div className="pillValue">
            <span className={`badge ${customEnabled ? "saved" : "unsaved"}`}>
              {customEnabled ? "ENABLED" : "DISABLED"}
            </span>
            {customDirty && (
              <span className="badge unsaved" style={{ marginLeft: 8 }}>
                UNSAVED
              </span>
            )}
          </div>
        </div>

        <div className="btnRow">
          <button
            className={`btn ${customEnabled ? "activeBtn" : ""}`}
            onClick={() => {
              setCustomEnabled((v) => !v);
              setCustomDirty(true);
            }}
          >
            {customEnabled ? "CUSTOM: ON" : "CUSTOM: OFF"}
          </button>

          <button className="btn" onClick={applyRecommended}>
            USE RECOMMENDED
          </button>
        </div>

        <div className="configGrid">
          <div>
            <label className="mini">Chunk Size</label>
            <input
              type="number"
              className="qinput"
              value={customConfig.chunk_size}
              onChange={(e) =>
                updateCustomField("chunk_size", parseInt(e.target.value))
              }
              min="100"
              max="2000"
              step="50"
            />
          </div>

          <div>
            <label className="mini">Overlap</label>
            <input
              type="number"
              className="qinput"
              value={customConfig.overlap}
              onChange={(e) =>
                updateCustomField("overlap", parseInt(e.target.value))
              }
              min="0"
              max="500"
              step="10"
            />
          </div>

          <div>
            <label className="mini">Top K</label>
            <input
              type="number"
              className="qinput"
              value={customConfig.top_k}
              onChange={(e) =>
                updateCustomField("top_k", parseInt(e.target.value))
              }
              min="1"
              max="20"
            />
          </div>

          <div>
            <label className="mini">Search Type</label>
            <select
              className="qinput"
              value={customConfig.search_type}
              onChange={(e) => updateCustomField("search_type", e.target.value)}
            >
              <option value="similarity">Similarity</option>
              <option value="mmr">MMR</option>
              <option value="similarity_score_threshold">
                Similarity Score Threshold
              </option>
            </select>
          </div>
        </div>

        <button
          className="btn activeBtn"
          onClick={saveCustomPipeline}
          disabled={!collectionId || customSaving}
        >
          {customSaving
            ? "SAVING..."
            : customDirty
              ? "SAVE CUSTOM PIPELINE*"
              : "SAVE CUSTOM PIPELINE"}
        </button>

        <div className="mini" style={{ marginTop: 4 }}>
          In Compare mode: system runs 4 defaults + (optional) this custom
          pipeline.
        </div>

        <div className="mini" style={{ marginTop: 4, fontStyle: "italic" }}>
          Note: Chunk settings are display-only. Custom pipeline uses Balanced
          chunks (800) with your Top-K and Search Type.
        </div>

        <div className="mini">
          Current: {customConfig.chunk_size}ch | {customConfig.overlap}ov | k
          {customConfig.top_k} | {customConfig.search_type}
        </div>
      </div>,
    );

  const WorkspaceCard = () =>
    brutalCard(
      "WORKSPACE",
      <div className="stack">
        <div className="pill">
          <div className="pillLabel">ACTIVE COLLECTION</div>
          <div className="pillValue">
            {collectionId
              ? `${activeCollectionName} (${collectionId.slice(0, 8)})`
              : "NONE"}
          </div>
        </div>

        <select
          className="qinput"
          value={collectionId}
          onChange={(e) => {
            setCollectionId(e.target.value);
            setAskRes(null);
            setUploadRes(null);
            setShowDashboard(false);
            setShowPdfViewer(false);
            setActivePdfUrl("");
            setActivePdfName("");
            setError("");
          }}
        >
          <option value="">-- Select Collection --</option>
          {collections.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} ({c.id.slice(0, 8)})
            </option>
          ))}
        </select>

        <div className="btnRow">
          <button className="btn" onClick={fetchCollections} disabled={!user}>
            REFRESH
          </button>
          <button
            className="btn"
            onClick={renameCollection}
            disabled={!user || !collectionId}
          >
            RENAME
          </button>
          <button
            className="btn danger"
            onClick={deleteCollection}
            disabled={!user || !collectionId}
          >
            DELETE
          </button>
        </div>

        <input
          className="file"
          type="file"
          accept="application/pdf"
          multiple
          onChange={(e) => setFiles(Array.from(e.target.files || []))}
        />

        <button
          className="btn activeBtn"
          onClick={uploadMultiPDF}
          disabled={!user || uploading || files.length === 0}
        >
          {uploading
            ? "UPLOADING + BUILDING..."
            : `UPLOAD ${files.length} PDF(s)`}
        </button>

        {uploadRes && (
          <div className="mini">
            Uploaded: <b>{uploadRes.files_uploaded?.length}</b> file(s) <br />
            Collection: <b>{uploadRes.collection_id}</b> <br />
            Time: <b>{uploadRes.total_time_taken_sec}s</b>
          </div>
        )}
      </div>,
    );

  const AskCard = () =>
    brutalCard(
      "ASK / CHAT",
      <div className="stack">
        <div className="btnRow">
          <button
            className={`btn ${mode === "chat" ? "activeBtn" : ""}`}
            onClick={() => setMode("chat")}
          >
            CHAT
          </button>
          <button
            className={`btn ${mode === "fast" ? "activeBtn" : ""}`}
            onClick={() => setMode("fast")}
          >
            FAST
          </button>
          <button
            className={`btn ${mode === "compare" ? "activeBtn" : ""}`}
            onClick={() => setMode("compare")}
          >
            COMPARE
          </button>
        </div>

        {mode === "chat" && (
          <div className="chatBox">
            {chatMessages.length === 0 ? (
              <div className="mini">
                Start chatting. This mode remembers context.
              </div>
            ) : (
              chatMessages.map((m, i) => (
                <div key={i} className="chatLine">
                  <b>{m.role === "user" ? "YOU" : "AI"}:</b> {m.message}
                </div>
              ))
            )}
          </div>
        )}

        <input
          className="qinput"
          placeholder={
            mode === "chat"
              ? "Type message..."
              : mode === "fast"
                ? "Ask for quick analysis..."
                : "Ask to compare all pipelines..."
          }
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleUnifiedQuery()}
        />

        <div className="btnRow">
          <button
            className="btn activeBtn"
            onClick={handleUnifiedQuery}
            disabled={!user || !collectionId || asking || chatLoading}
          >
            {asking || chatLoading
              ? "PROCESSING..."
              : mode === "chat"
                ? "SEND"
                : "ASK"}
          </button>

          {mode === "chat" && (
            <>
              <button
                className="btn"
                onClick={fetchChat}
                disabled={!collectionId}
              >
                REFRESH
              </button>
              <button
                className="btn danger"
                onClick={clearChat}
                disabled={!collectionId}
              >
                CLEAR
              </button>
            </>
          )}

          {askRes && mode !== "chat" && (
            <button
              className={`btn ${showDashboard ? "danger" : ""}`}
              onClick={() => setShowDashboard((s) => !s)}
            >
              {showDashboard ? "HIDE RESULTS" : "SHOW RESULTS"}
            </button>
          )}

          {indexMissing && (
            <button
              className="btn warning"
              onClick={rebuildIndex}
              disabled={rebuildingIndex}
              style={{ backgroundColor: "#ff9800", color: "white" }}
            >
              {rebuildingIndex ? "REBUILDING..." : "🔧 REBUILD INDEX"}
            </button>
          )}
        </div>
      </div>,
    );

  const ImageTestCard = () =>
    brutalCard(
      "IMAGE TEST MODE (RAG VISION ACCURACY)",
      <div className="stack">
        <div className="mini">
          Upload an image and ask a question to test vision accuracy.
        </div>

        <input
          className="file"
          type="file"
          accept="image/*"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            setImgFile(f);
            setImgPreview(URL.createObjectURL(f));
            setImgRes(null);
          }}
        />

        {imgPreview && (
          <img src={imgPreview} alt="preview" className="imgPreview" />
        )}

        <input
          className="qinput"
          value={imgQuestion}
          onChange={(e) => setImgQuestion(e.target.value)}
          placeholder="Ask something about the image..."
        />

        <div className="btnRow">
          <button
            className="btn activeBtn"
            disabled={imgLoading || !imgFile || !imgQuestion.trim()}
            onClick={async () => {
              setError("");
              setImgLoading(true);
              setImgRes(null);

              try {
                const api = await axiosAuth();
                const fd = new FormData();
                fd.append("image", imgFile);
                fd.append("question", imgQuestion.trim());
                if (collectionId) fd.append("collection_id", collectionId);

                const res = await api.post("/image-test", fd, {
                  headers: { "Content-Type": "multipart/form-data" },
                });

                setImgRes(res.data);
              } catch (err) {
                console.error("Image test error:", err);
                setError("Image test failed. Check backend logs.");
              } finally {
                setImgLoading(false);
              }
            }}
          >
            {imgLoading ? "ANALYZING..." : "ANALYZE IMAGE"}
          </button>

          <button
            className="btn"
            onClick={() => setShowImgAdvanced((s) => !s)}
            disabled={!imgRes}
          >
            {showImgAdvanced ? "HIDE METRICS" : "SHOW METRICS"}
          </button>

          <button
            className="btn danger"
            onClick={() => {
              setImgFile(null);
              setImgPreview("");
              setImgQuestion("");
              setImgRes(null);
              setShowImgAdvanced(false);
            }}
          >
            CLEAR
          </button>
        </div>

        {imgRes && (
          <div className="stack">
            <div className="pill">
              <div className="pillLabel">CONFIDENCE</div>
              <div className="pillValue">
                <span className="confidenceBadge">
                  {Number(imgRes.confidence_score ?? 0).toFixed(1)} / 10
                </span>
              </div>
            </div>

            <div className="finalAnswer">
              <b>Answer:</b> {imgRes.final_answer}
            </div>

            <div className="mini">
              <b>Extracted Description:</b>
              <br />
              {imgRes.extracted_description}
            </div>

            {showImgAdvanced && (
              <div className="pill">
                <div className="pillLabel">METRICS</div>
                <div className="mini">
                  Vision: {imgRes.metrics?.latency?.vision_ms ?? 0} ms
                  <br />
                  LLM: {imgRes.metrics?.latency?.llm_ms ?? 0} ms
                  <br />
                  Total: {imgRes.metrics?.latency?.total_ms ?? 0} ms
                  <br />
                  <br />
                  Tokens: {imgRes.metrics?.tokens?.total_tokens ?? 0}
                  <br />
                  Cost ($): {imgRes.metrics?.tokens?.estimated_cost_usd ?? 0}
                </div>
              </div>
            )}
          </div>
        )}
      </div>,
    );

  const ResultsDashboard = () => {
    if (!showDashboard || !askRes || mode === "chat") return null;

    return (
      <div className="dashboardPanel">
        <div className="dashboardHeader">
          <div>RESULTS & ANALYSIS</div>
          <button
            className="btn danger"
            onClick={() => setShowDashboard(false)}
          >
            CLOSE
          </button>
        </div>

        <div className="dashboardBody">
          <div className="pill" style={{ marginBottom: 12 }}>
            <div className="pillLabel">BEST PIPELINE</div>
            <div className="pillValue">{askRes.best_pipeline}</div>
          </div>

          <div className="finalAnswer">{askRes.final_answer}</div>

          {/* ✅ PERFORMANCE BREAKDOWN */}
          <div className="perfCard" style={{ marginTop: 14 }}>
            <div className="perfTitle">PERFORMANCE BREAKDOWN</div>

            <div className="perfGrid">
              <div className="perfBlock">
                <div className="perfBlockTitle">LATENCY</div>
                <div className="perfRow">
                  <span>Embedding</span>
                  <b>{fmtMs(safeMetrics?.timings_ms?.embedding_ms)}</b>
                </div>
                <div className="perfRow">
                  <span>Retrieval</span>
                  <b>{fmtMs(safeMetrics?.timings_ms?.retrieval_ms)}</b>
                </div>
                <div className="perfRow">
                  <span>Rerank</span>
                  <b>{fmtMs(safeMetrics?.timings_ms?.rerank_ms)}</b>
                </div>
                <div className="perfRow">
                  <span>LLM</span>
                  <b>{fmtMs(safeMetrics?.timings_ms?.llm_ms)}</b>
                </div>
                <div className="perfRow">
                  <span>Total</span>
                  <b>{fmtMs(safeMetrics?.timings_ms?.total_ms)}</b>
                </div>
              </div>

              <div className="perfBlock">
                <div className="perfBlockTitle">TOKENS + COST</div>
                <div className="perfRow">
                  <span>Prompt Tokens</span>
                  <b>{fmtNum(safeMetrics?.tokens?.prompt_tokens)}</b>
                </div>
                <div className="perfRow">
                  <span>Completion Tokens</span>
                  <b>{fmtNum(safeMetrics?.tokens?.completion_tokens)}</b>
                </div>
                <div className="perfRow">
                  <span>Total Tokens</span>
                  <b>{fmtNum(safeMetrics?.tokens?.total_tokens)}</b>
                </div>
                <div className="perfRow">
                  <span>Estimated Cost</span>
                  <b>{fmtMoney(safeMetrics?.cost_usd)}</b>
                </div>
                <div className="perfRow">
                  <span>Model</span>
                  <b>{safeMetrics?.tokens?.model || "unknown"}</b>
                </div>
                <div className="perfRow">
                  <span>Cache Hit</span>
                  <b>{String(safeMetrics?.cache_hit ?? false)}</b>
                </div>
              </div>
            </div>

            {safeMetrics?.timings_ms && (
              <div className="perfChartWrap">
                <div className="perfBlockTitle">LATENCY STAGES (VISUAL)</div>
                <div className="chartCanvas">
                  <Bar data={latencyChart} options={brutalistChartOptions} />
                </div>
              </div>
            )}
          </div>

          {askRes?.retrieval_comparison?.length > 0 && (
            <div className="charts4">
              <div className="chartBox">
                <div className="chartTitle">RETRIEVAL SPEED</div>
                <div className="chartCanvas">
                  <Bar data={retrievalChart} options={brutalistChartOptions} />
                </div>
              </div>
              <div className="chartBox">
                <div className="chartTitle">RELEVANCE + GROUNDED</div>
                <div className="chartCanvas">
                  <Bar data={scoreChart} options={brutalistChartOptions} />
                </div>
              </div>
              <div className="chartBox">
                <div className="chartTitle">QUALITY vs EFFICIENCY</div>
                <div className="chartCanvas">
                  <Bar
                    data={qualityEfficiencyChart}
                    options={brutalistChartOptions}
                  />
                </div>
              </div>
              <div className="chartBox">
                <div className="chartTitle">FINAL SCORE</div>
                <div className="chartCanvas">
                  <Bar data={finalScoreChart} options={brutalistChartOptions} />
                </div>
              </div>
            </div>
          )}

          {askRes?.retrieval_comparison?.length > 0 && (
            <div className="pipeGrid">
              {askRes.retrieval_comparison.map((p, idx) => {
                const isCustom =
                  p.pipeline && p.pipeline.toLowerCase().includes("custom");
                const pipelineLabel = labelForIndex(idx);

                return (
                  <div
                    key={idx}
                    className={`pipeCard ${idx === 0 ? "winner" : ""}`}
                  >
                    <div className="pipeTop">
                      <div className="pipeRank">{pipelineLabel}</div>
                      <div className="pipeScore">{p.scores?.final ?? 0}</div>
                    </div>

                    <div className="pipeName">
                      Pipeline {pipelineLabel}
                      <div className="pipeSubname">{p.pipeline}</div>
                    </div>

                    <div className="pipeDetailsGrid">
                      <div className="pipeDetail">
                        <b>Chunk:</b> {p.chunk_size}
                      </div>
                      <div className="pipeDetail">
                        <b>Overlap:</b> {p.overlap}
                      </div>
                      <div className="pipeDetail">
                        <b>Top-K:</b> {p.top_k}
                      </div>
                      <div className="pipeDetail">
                        <b>Search:</b> {p.search_type}
                      </div>
                      <div className="pipeDetail">
                        <b>Retrieval:</b> {p.retrieval_time_sec}s
                      </div>
                      <div className="pipeDetail">
                        <b>Build:</b> {p.build_time_sec ?? "N/A"}s
                      </div>
                      <div className="pipeDetail">
                        <b>Chunks:</b> {p.chunks_created ?? "N/A"}
                      </div>
                      <div className="pipeDetail">
                        <b>R:</b> {p.scores?.relevance ?? 0} | <b>G:</b>{" "}
                        {p.scores?.grounded ?? 0}
                      </div>
                      <div className="pipeDetail">
                        <b>Q:</b> {p.scores?.quality ?? 0} | <b>E:</b>{" "}
                        {p.scores?.efficiency ?? 0}
                      </div>
                    </div>

                    {p.context_preview && (
                      <div className="contextMini">
                        <b>Context:</b>{" "}
                        {p.context_preview.length > 160
                          ? p.context_preview.slice(0, 160) + "..."
                          : p.context_preview}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          <div className="btnRow" style={{ marginTop: 14 }}>
            <button
              className="btn"
              onClick={downloadReportTXT}
              disabled={downloadingReport}
            >
              {downloadingReport ? "GENERATING..." : "EXPORT TXT"}
            </button>

            <button
              className="btn"
              onClick={downloadReportJSON}
              disabled={downloadingReport}
            >
              EXPORT JSON
            </button>

            <button
              className="btn"
              onClick={downloadReportCSV}
              disabled={downloadingReport}
            >
              EXPORT CSV
            </button>

            <button
              className="btn activeBtn"
              onClick={() => {
                if (!collectionId) return;
                if (!collectionFiles.length) fetchCollectionFiles();
                setShowPdfViewer((s) => !s);
                if (!activePdfUrl) openPdfInViewer({ page: null });
              }}
            >
              {showPdfViewer ? "HIDE PDF" : "OPEN PDF"}
            </button>

            <button
              className="btn"
              onClick={() => {
                setChunkExplorerOpen(true);
                setChunkOffset(0);
                fetchChunks();
              }}
              disabled={!collectionId}
            >
              CHUNK EXPLORER
            </button>
          </div>

          {showPdfViewer && activePdfUrl && (
            <div className="pdfWrap">
              <div className="mini">
                Viewing: <b>{activePdfName || "PDF"}</b>
              </div>
              <iframe title="PDF Preview" src={activePdfUrl} />
            </div>
          )}
        </div>
      </div>
    );
  };

  const LeaderboardCard = () =>
    brutalCard(
      "LEADERBOARD",
      <div className="stack">
        <div className="leaderMeta">
          <span className="leaderBadge">
            MODE: {leaderboardMode.toUpperCase()}
          </span>
          <span className="leaderBadge">
            RANGE: {leaderboardRange.toUpperCase()}
          </span>
        </div>

        <div className="btnRow">
          {["all", "fast", "compare", "chat"].map((m) => (
            <button
              key={m}
              className={`btn ${leaderboardMode === m ? "activeBtn" : ""}`}
              onClick={() => setLeaderboardMode(m)}
            >
              {m.toUpperCase()}
            </button>
          ))}
        </div>

        <div className="btnRow">
          {["7d", "30d", "all"].map((r) => (
            <button
              key={r}
              className={`btn ${leaderboardRange === r ? "activeBtn" : ""}`}
              onClick={() => setLeaderboardRange(r)}
            >
              {r.toUpperCase()}
            </button>
          ))}
        </div>

        <div className="btnRow">
          <button
            className="btn activeBtn"
            onClick={fetchLeaderboard}
            disabled={!collectionId || leaderboardLoading}
          >
            {leaderboardLoading ? "LOADING..." : "REFRESH"}
          </button>

          <button
            className="btn"
            onClick={() => setBatchOpen(true)}
            disabled={!collectionId}
          >
            BATCH EVAL
          </button>
        </div>

        {!leaderboard ? (
          <div className="mini">Ask questions to generate stats.</div>
        ) : (
          <div className="stack">
            <div className="mini">
              Total Questions: <b>{leaderboard.total_questions}</b>
            </div>
            <div className="mini">
              Chat Interactions: <b>{leaderboard.chat_interactions || 0}</b>
            </div>
            <div className="mini">
              Best Today: <b>{leaderboard.best_pipeline_today || "N/A"}</b>
            </div>

            <div style={{ marginTop: 6 }}>
              {leaderboard.pipelines?.map((p, i) => {
                // Try to map pipeline name to label
                const pipelineLabel = labelForIndex(i);

                return (
                  <div
                    key={i}
                    className={`leaderRow ${i === 0 ? "leaderRowStrong" : ""}`}
                  >
                    <div className="leaderRank">{pipelineLabel}</div>
                    <div style={{ flex: 1 }}>
                      <b>Pipeline {pipelineLabel}</b>
                      <div className="mini" style={{ opacity: 0.7 }}>
                        {p.pipeline}
                      </div>
                      <div className="mini">
                        Wins: <b>{p.wins}</b> ({(p.win_rate * 100).toFixed(1)}
                        %) | Avg Score: <b>{p.avg_final_score}</b>
                      </div>
                      <div className="mini">
                        Avg Time:{" "}
                        <b>
                          {p.avg_total_time_sec > 0
                            ? p.avg_total_time_sec
                            : p.avg_retrieval_time_sec}
                          s
                        </b>
                        {p.avg_llm_time_sec > 0 && (
                          <span> (LLM: {p.avg_llm_time_sec}s)</span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>,
    );

  const ChunkExplorerCard = () => {
    if (!chunkExplorerOpen) return null;

    return brutalCard(
      "CHUNK EXPLORER (DEBUG)",
      <div className="stack">
        <div className="chunkToolbar">
          <input
            className="qinput"
            placeholder="Search chunk text..."
            value={chunkQuery}
            onChange={(e) => {
              setChunkQuery(e.target.value);
              setChunkOffset(0);
            }}
          />

          <div className="chunkFilters">
            <input
              className="qinput"
              placeholder="Filter by page (e.g. 3)"
              value={chunkFilterPage}
              onChange={(e) => {
                setChunkFilterPage(e.target.value);
                setChunkOffset(0);
              }}
            />

            <input
              className="qinput"
              placeholder="Filter pipeline (optional)"
              value={chunkFilterPipeline}
              onChange={(e) => {
                setChunkFilterPipeline(e.target.value);
                setChunkOffset(0);
              }}
            />
          </div>

          <div className="btnRow">
            <button
              className="btn activeBtn"
              onClick={fetchChunks}
              disabled={chunksLoading}
            >
              {chunksLoading ? "LOADING..." : "REFRESH CHUNKS"}
            </button>
            <button
              className="btn danger"
              onClick={() => setChunkExplorerOpen(false)}
            >
              CLOSE
            </button>
          </div>

          <div className="mini">
            Showing <b>{chunks.length}</b> of <b>{chunksTotal}</b> chunks
          </div>
        </div>

        <div className="chunkList">
          {chunksLoading ? (
            <div className="mini">Loading chunks...</div>
          ) : chunks.length === 0 ? (
            <div className="mini">No chunks found.</div>
          ) : (
            chunks.map((c) => (
              <div key={c.id} className="chunkCard">
                <div className="chunkMeta">
                  <div>
                    <b>File:</b> {c.filename || "PDF"}
                  </div>
                  <div>
                    <b>Page:</b> {c.page_number ?? "—"}
                  </div>
                  <div>
                    <b>Chunk #:</b> {c.chunk_index ?? "—"}
                  </div>
                  <div>
                    <b>Pipeline:</b> {c.pipeline_name || "—"}
                  </div>
                </div>

                <div className="chunkText">
                  {c.chunk_text?.length > 260
                    ? c.chunk_text.slice(0, 260) + "..."
                    : c.chunk_text}
                </div>

                <div className="btnRow">
                  <button
                    className="btn"
                    onClick={() => {
                      if (!collectionFiles.length) fetchCollectionFiles();
                      setShowPdfViewer(true);
                      openPdfInViewer({
                        fileId: c.file_id,
                        page: c.page_number ?? 0,
                      });
                    }}
                  >
                    OPEN PDF @ PAGE {c.page_number ?? 0}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="chunkPager">
          <button
            className="btn"
            disabled={chunkOffset <= 0}
            onClick={() => {
              setChunkOffset((o) => Math.max(0, o - chunkLimit));
            }}
          >
            PREV
          </button>

          <div className="mini" style={{ margin: "0 10px" }}>
            Page {Math.floor(chunkOffset / chunkLimit) + 1} of{" "}
            {Math.ceil(chunksTotal / chunkLimit)}
          </div>

          <button
            className="btn"
            disabled={chunkOffset + chunkLimit >= chunksTotal}
            onClick={() => {
              setChunkOffset((o) => o + chunkLimit);
            }}
          >
            NEXT
          </button>
        </div>
      </div>,
    );
  };

  const BatchEvalCard = () => {
    if (!batchOpen) return null;

    return brutalCard(
      "BATCH EVALUATION (TEST SET)",
      <div className="stack">
        <div className="btnRow">
          <button
            className={`btn ${batchMode === "fast" ? "activeBtn" : ""}`}
            onClick={() => setBatchMode("fast")}
          >
            FAST MODE
          </button>
          <button
            className={`btn ${batchMode === "compare" ? "activeBtn" : ""}`}
            onClick={() => setBatchMode("compare")}
          >
            COMPARE MODE
          </button>
        </div>

        <div className="mini">
          Paste JSON test set below. Format:{" "}
          {`{"items": [{"question": "...", "expected_answer": "..."}]}`}
        </div>

        <textarea
          className="batchTextArea"
          placeholder='{"items": [{"question": "What is X?", "expected_answer": "..."}]}'
          value={batchDatasetText}
          onChange={(e) => setBatchDatasetText(e.target.value)}
          disabled={batchRunning}
        />

        <div className="btnRow">
          <button
            className="btn"
            onClick={parseBatchDataset}
            disabled={batchRunning || !batchDatasetText}
          >
            PARSE DATASET
          </button>

          <div className="mini">
            Parsed: <b>{batchItems.length}</b> questions
          </div>
        </div>

        <div className="btnRow">
          <button
            className="btn activeBtn"
            onClick={runBatchEval}
            disabled={batchRunning || !batchItems.length || !collectionId}
          >
            {batchRunning ? "RUNNING..." : "▶ RUN EVALUATION"}
          </button>

          {batchProgress && (
            <button
              className="btn"
              onClick={downloadBatchReport}
              disabled={batchRunning}
            >
              EXPORT JSON
            </button>
          )}

          <button
            className="btn danger"
            onClick={() => {
              setBatchOpen(false);
              stopBatchPolling();
            }}
          >
            CLOSE
          </button>
        </div>

        {batchProgress && (
          <div className="stack" style={{ marginTop: 12 }}>
            <div className="pill">
              <div className="pillLabel">PROGRESS</div>
              <div className="pillValue">
                {batchProgress.completed_questions} /{" "}
                {batchProgress.total_questions}
              </div>
            </div>

            <div className="pill">
              <div className="pillLabel">AVG SCORE</div>
              <div className="pillValue">
                {batchProgress.avg_final_score.toFixed(2)}
              </div>
            </div>

            <div className="pill">
              <div className="pillLabel">STATUS</div>
              <div className="pillValue">
                {batchProgress.status.toUpperCase()}
              </div>
            </div>

            {batchProgress.items && batchProgress.items.length > 0 && (
              <div className="batchTable">
                <div
                  className="batchRow"
                  style={{ background: "#f0f0f0", fontWeight: "900" }}
                >
                  <div>QUESTION</div>
                  <div>PIPELINE</div>
                  <div>SCORE</div>
                  <div>TOKENS</div>
                </div>

                {batchProgress.items.map((item, idx) => (
                  <div key={idx} className="batchRow">
                    <div style={{ fontWeight: "800" }}>
                      {item.question.length > 50
                        ? item.question.slice(0, 50) + "..."
                        : item.question}
                    </div>
                    <div>{item.best_pipeline || "—"}</div>
                    <div>{item.scores?.final_score?.toFixed(1) || "—"}</div>
                    <div>{item.tokens?.total_tokens || 0}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>,
    );
  };

  // --------------------------------
  // SaaS Render
  // --------------------------------
  return (
    <div className="appShell">
      <header className="topBar">
        <div className="logo">RAG OPTIMIZER</div>
        <div className="topProfile">
          {user ? (
            <>
              <span className="profileIcon">👤</span>
              {user.user_metadata?.full_name ||
                user.user_metadata?.name ||
                user.email?.split("@")[0] ||
                "User"}
            </>
          ) : (
            "Not signed in"
          )}
        </div>
      </header>

      {error && <div className="topError">{error}</div>}

      <div className="appBody">
        <aside className="sidebar">
          {ProfileAuthCard()}
          {CustomPipelineCard()}
          {WorkspaceCard()}
        </aside>

        <main className="workspace">
          {AskCard()}
          {ImageTestCard()}
          {ResultsDashboard()}
          {ChunkExplorerCard()}
          {BatchEvalCard()}
          {LeaderboardCard()}
        </main>
      </div>
    </div>
  );
}
