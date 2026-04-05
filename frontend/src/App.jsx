import {
  useEffect,
  useState,
  useMemo,
  useRef,
  useCallback,
  Component,
  Fragment,
} from "react";
import axios from "axios";
import toast, { Toaster } from "react-hot-toast";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./ModernApp.css";
import TreeViewer from "./TreeViewer";
import Silk from "./components/Silk";
import { FastModeResults } from "./components/FastModeResults";
import { CompareModeResults } from "./components/CompareModeResults";
import { DetailedMetricsPanel } from "./components/DetailedMetricsPanel";
import { About } from "./pages/About";
import { Documentation } from "./pages/Documentation";

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

import { jsPDF } from "jspdf";

import {
  MessageSquare,
  Image,
  Settings,
  Trophy,
  Search,
  Paperclip,
  RefreshCw,
  Trash2,
  BarChart3,
  Wrench,
  Zap,
  FlaskConical,
  Pencil,
  Sun,
  Moon,
  Plus,
  X,
  ArrowUp,
  LogIn,
  LogOut,
  Upload,
  FileText,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Sparkles,
  Copy,
  AlertTriangle,
  PanelLeftClose,
  PanelLeftOpen,
  Download,
} from "lucide-react";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8002";

// Module-level session cache — avoids a Supabase round-trip on every API call
let _sessionToken = null;
let _sessionExpiry = 0;

async function getCachedSession() {
  const now = Date.now();
  if (_sessionToken && now < _sessionExpiry) return _sessionToken;
  // Re-validate with Supabase and grab a fresh token
  const { data: userData, error: userError } = await supabase.auth.getUser();
  if (userError || !userData?.user) return null;
  const { data } = await supabase.auth.getSession();
  const session = data?.session;
  const token = session?.access_token;
  if (!token) return null;
  // If token expires within 60s, force a refresh now
  const expiresAt = (session.expires_at ?? 0) * 1000;
  if (expiresAt && expiresAt - now < 60_000) {
    const { data: refreshed } = await supabase.auth.refreshSession();
    const freshToken = refreshed?.session?.access_token;
    if (!freshToken) return null;
    _sessionToken = freshToken;
    _sessionExpiry = now + 50_000;
    return freshToken;
  }
  _sessionToken = token;
  _sessionExpiry = now + 50_000; // 50-second TTL
  return token;
}

// Extract error message from various backend response formats
function extractErrorMessage(error, fallback = "An error occurred") {
  // Handle axios error response
  if (error?.response?.data) {
    const data = error.response.data;
    // Simple string error
    if (typeof data?.detail === "string") {
      return data.detail;
    }
    // Array of validation errors (Pydantic format)
    if (Array.isArray(data?.detail)) {
      const msgs = data.detail.map((err) => {
        if (typeof err === "string") return err;
        if (err?.msg) return err.msg;
        return "Validation error";
      });
      return msgs.join("; ");
    }
    // Complex object error
    if (typeof data?.detail === "object" && data?.detail?.msg) {
      return data.detail.msg;
    }
  }
  // Handle other error formats
  if (error?.message) return error.message;
  return fallback;
}

// ── Error Boundary ──
class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, info) {
    console.error("ErrorBoundary caught:", error, info);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            minHeight: "100vh",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "#F5F5F0",
            fontFamily: "Georgia, serif",
          }}
        >
          <div style={{ textAlign: "center", maxWidth: 420, padding: 40 }}>
            <AlertTriangle
              size={48}
              style={{ color: "#d9534f", marginBottom: 16 }}
            />
            <h2 style={{ marginBottom: 8 }}>Something went wrong</h2>
            <p style={{ color: "#6b6a68", fontSize: 14, marginBottom: 20 }}>
              {this.state.error?.message || "An unexpected error occurred."}
            </p>
            <button
              onClick={() => window.location.reload()}
              style={{
                padding: "10px 24px",
                background: "#ae5630",
                color: "#fff",
                border: "none",
                borderRadius: 10,
                cursor: "pointer",
                fontFamily: "Georgia, serif",
                fontSize: 14,
              }}
            >
              Reload App
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
export { ErrorBoundary };

// ✅ Pipeline short labels — name-keyed map so charts and cards are readable
const PIPELINE_SHORT_LABELS = {
  "Balanced (MMR)": "1 (Balanced)",
  "Fastest (Similarity)": "2 (Fastest)",
  "Accurate (Similarity + Larger k)": "3 (Accurate)",
  "DeepSearch (MMR + Higher k)": "4 (DeepSearch)",
  "Custom User Pipeline": "5 (Custom)",
};
const shortLabel = (name) => PIPELINE_SHORT_LABELS[name] || name;

export default function App() {
  // ✅ AUTH
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  // Toast replaces old error state — kept for minor internal use only
  const [error, setError] = useState("");
  const [showAbout, setShowAbout] = useState(false); // Show about page instead of login
  const [showDocumentation, setShowDocumentation] = useState(false); // Show documentation page

  // ✅ MODE
  const [mode, setMode] = useState("chat"); // chat | fast | compare | image

  // ✅ CLAUDE UI
  const [darkMode, setDarkMode] = useState(() => {
    try {
      const saved = localStorage.getItem("rag-theme");
      if (saved) return saved === "dark";
      return (
        window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false
      );
    } catch {
      return false;
    }
  });
  const [activeTool, setActiveTool] = useState("chat"); // chat | image | config | leaderboard | chunks
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [modeMenuOpen, setModeMenuOpen] = useState(false);

  // ✅ TIMERS
  const uploadTimerRef = useRef(null);
  const [uploadElapsed, setUploadElapsed] = useState(0);
  const queryTimerRef = useRef(null);
  const [queryElapsed, setQueryElapsed] = useState(0);
  const threadRef = useRef(null);
  const modeMenuRef = useRef(null);

  // ✅ COLLECTIONS
  const [collectionId, setCollectionId] = useState("");
  const [collections, setCollections] = useState([]);

  // ✅ UPLOAD
  const [files, setFiles] = useState([]);
  const [uploadRes, setUploadRes] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [forceNewCollection, setForceNewCollection] = useState(false); // true = "+" new chat, false = paperclip add-to-existing
  const [indexType, setIndexType] = useState("vector"); // "vector" or "tree"

  // ✅ SIDEBAR
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // ✅ ASK / CHAT
  const [question, setQuestion] = useState("");
  const [pendingQuestion, setPendingQuestion] = useState(""); // holds question text while awaiting response
  const [askRes, setAskRes] = useState(null);
  const [asking, setAsking] = useState(false);
  const [lastQueryResult, setLastQueryResult] = useState(null); // persist most recent query result
  const [lastQueryTimestamp, setLastQueryTimestamp] = useState(null); // timestamp of last query

  // ✅ CHAT
  const [chatMessages, setChatMessages] = useState([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatHistoryLoading, setChatHistoryLoading] = useState(false);
  const [chatCache, setChatCache] = useState({}); // { [collectionId]: messages[] }
  const [chatAnalytics, setChatAnalytics] = useState({}); // { [msgIndex]: {pipeline, latency_ms, docs_retrieved, smart_extract} }
  const [showAllPipelines, setShowAllPipelines] = useState(false);
  const [fastHistory, setFastHistory] = useState([]); // past fast/compare Q&A for the active collection
  const [chatDisplayLimit, setChatDisplayLimit] = useState(40); // cap rendered messages for perf

  // ✅ FILES + PDF VIEWER
  const [collectionFiles, setCollectionFiles] = useState([]);
  const [showDocBar, setShowDocBar] = useState(false);
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

  const [presetApplying, setPresetApplying] = useState(false);

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
  const [customLoading, setCustomLoading] = useState(false);
  const [indexMissing, setIndexMissing] = useState(false);
  const [rebuildingIndex, setRebuildingIndex] = useState(false);

  // ✅ CHUNK EXPLORER (DEBUG TOOL)
  const [chunkExplorerOpen, setChunkExplorerOpen] = useState(false);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [chunks, setChunks] = useState([]);
  const [chunksTotal, setChunksTotal] = useState(0);
  const [treeLoading, setTreeLoading] = useState(false);
  const [treeData, setTreeData] = useState(null);
  const [treeExpanded, setTreeExpanded] = useState({});
  const [treeError, setTreeError] = useState("");
  const [chunkQuery, setChunkQuery] = useState("");
  const [chunkFilterPipeline, setChunkFilterPipeline] = useState("");
  const [chunkFilterFileId] = useState("");
  const [chunkFilterPage, setChunkFilterPage] = useState("");
  const [chunkOffset, setChunkOffset] = useState(0);
  const [chunkLimit] = useState(20);
  const [knownPipelines, setKnownPipelines] = useState([]);

  // ✅ IMAGE TEST MODE (RAG VISION ACCURACY)
  const [imgFile, setImgFile] = useState(null);
  const [imgPreview, setImgPreview] = useState("");
  const [imgQuestion, setImgQuestion] = useState("");
  const [imgLoading, setImgLoading] = useState(false);
  const [imgRes, setImgRes] = useState(null);
  const [showImgAdvanced, setShowImgAdvanced] = useState(false);

  // ✅ CUSTOM MODALS (rename / delete / clear chat)
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deletingCollection, setDeletingCollection] = useState(false);
  const [clearChatModalOpen, setClearChatModalOpen] = useState(false);

  // ✅ MODEL SELECTION & MANAGEMENT
  const [availableModels, setAvailableModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState(null);
  const [modelSelectionOpen, setModelSelectionOpen] = useState(false);
  const [addModelMode, setAddModelMode] = useState(false);
  const [editingModelId, setEditingModelId] = useState(null);
  const [modelFormData, setModelFormData] = useState({
    model_name: "",
    provider: "openai",
    api_url: "",
    api_key: "",
    temperature: 0.7,
  });
  const [testingConnectivity, setTestingConnectivity] = useState(false);
  const [savingModel, setSavingModel] = useState(false);

  // ✅ COLLECTION SEARCH
  const [collectionSearch, setCollectionSearch] = useState("");

  // ✅ UPLOAD PROGRESS
  const [uploadProgress, setUploadProgress] = useState(0);

  // ✅ DRAG STATE
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  // --------------------------------
  // Active Collection Helpers
  // --------------------------------
  const activeCollection = useMemo(
    () => collections.find((c) => c.id === collectionId) || null,
    [collections, collectionId],
  );

  const activeCollectionName = useMemo(
    () => activeCollection?.name || "—",
    [activeCollection],
  );

  const activeCollectionIndexType = useMemo(
    () => (activeCollection?.index_type || "vector").toLowerCase(),
    [activeCollection],
  );

  // --------------------------------
  // Axios Auth
  // --------------------------------
  const axiosAuth = async () => {
    const token = await getCachedSession();
    if (!token) throw new Error("No active session. Please login.");

    const instance = axios.create({ baseURL: API });

    instance.interceptors.request.use((config) => {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
      return config;
    });

    // Response interceptor — handles auth failures AND backend-offline detection
    instance.interceptors.response.use(
      (res) => res,
      (err) => {
        if (!err.response) {
          // No response at all = backend is down / unreachable
          // Browsers misreport this as a CORS error — show the real cause instead
          toast.error("Backend is offline. Restart the server and try again.", {
            id: "backend-offline", // deduplicated — only one toast shown at a time
            duration: 6000,
          });
        } else if (err.response.status === 401) {
          // Bust the session cache so next call forces a fresh Supabase token
          _sessionToken = null;
          _sessionExpiry = 0;
          toast.error("Authentication failed. Please sign in again.");
        }
        return Promise.reject(err);
      },
    );

    return instance;
  };

  // --------------------------------
  // Auth UI helpers
  // --------------------------------
  const signInWithGoogle = async () => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
    });
    if (error) toast.error(error.message);
  };

  const fetchAvailableModels = async () => {
    try {
      const api = await axiosAuth();
      const res = await api.get(`/models`);
      const models = res.data.models || [];
      setAvailableModels(models);

      // Set the active model from the response
      const activeModel = models.find((m) => m.is_active);
      if (activeModel) {
        setSelectedModel(activeModel.id);
      } else if (models.length > 0) {
        // Fallback to first model if none is marked active
        setSelectedModel(models[0].id);
      }

      // Only open modal if no model is selected yet (first login scenario)
      if (!selectedModel && models.length > 1) {
        setModelSelectionOpen(true);
      }
    } catch (err) {
      console.error("fetchAvailableModels error", err);
      toast.error("Failed to load available models.");
    }
  };

  const setActiveModel = async (modelId) => {
    try {
      const api = await axiosAuth();
      console.log("Setting active model to:", modelId);
      const response = await api.put(`/models/active`, { model_id: modelId });
      console.log("Model updated successfully:", response.data);
      setSelectedModel(modelId);
      toast.success("Model updated.");
      // Delay closing modal slightly to show success message
      setTimeout(() => {
        setModelSelectionOpen(false);
      }, 500);
    } catch (err) {
      console.error("setActiveModel error", err);
      const errorMsg = err.response?.data?.detail || "Failed to update model.";
      toast.error(errorMsg);
    }
  };

  const resetModelForm = () => {
    setModelFormData({
      model_name: "",
      provider: "openai",
      api_url: "",
      api_key: "",
      temperature: 0.7,
    });
  };

  const startAddModel = () => {
    resetModelForm();
    setAddModelMode(true);
  };

  const cancelAddModel = () => {
    setAddModelMode(false);
    resetModelForm();
  };

  const addCustomModel = async () => {
    if (!modelFormData.model_name?.trim())
      return toast.error("Enter model name.");
    if (!modelFormData.api_url?.trim()) return toast.error("Enter API URL.");
    if (!modelFormData.api_key?.trim()) return toast.error("Enter API key.");

    setSavingModel(true);
    try {
      const api = await axiosAuth();
      await api.post("/models", {
        model_name: modelFormData.model_name,
        provider: modelFormData.provider,
        api_url: modelFormData.api_url,
        api_key: modelFormData.api_key,
        temperature: modelFormData.temperature,
      });

      toast.success("Custom model added!");
      setAddModelMode(false);
      resetModelForm();
      await fetchAvailableModels();
    } catch (err) {
      console.error("Add model error", err);
      toast.error(extractErrorMessage(err, "Failed to add model."));
    } finally {
      setSavingModel(false);
    }
  };

  const testModelConnectivity = async () => {
    if (!modelFormData.api_url?.trim())
      return toast.error("Enter API URL first.");
    if (!modelFormData.api_key?.trim())
      return toast.error("Enter API key first.");

    setTestingConnectivity(true);
    try {
      const api = await axiosAuth();
      await api.post("/models/test", {
        provider: modelFormData.provider,
        api_url: modelFormData.api_url,
        api_key: modelFormData.api_key,
      });
      toast.success("✓ Connection successful!");
    } catch (err) {
      console.error("Test connection error", err);
      toast.error(
        extractErrorMessage(err, "Connection failed. Check credentials."),
      );
    } finally {
      setTestingConnectivity(false);
    }
  };

  const deleteCustomModel = async (modelId) => {
    if (
      !window.confirm(
        "Delete this model? If it is active, you will be switched to the system default.",
      )
    )
      return;

    try {
      const api = await axiosAuth();
      await api.delete(`/models/${modelId}`);
      toast.success("Model deleted.");
      if (selectedModel === modelId) {
        const defaultModel = availableModels.find((m) => !m.is_custom);
        setSelectedModel(defaultModel?.id || null);
      }
      await fetchAvailableModels();
    } catch (err) {
      console.error("Delete model error", err);
      toast.error(extractErrorMessage(err, "Failed to delete model."));
    }
  };

  const startEditModel = (model) => {
    setModelFormData({
      model_name: model.model_name,
      provider: model.provider,
      api_url: model.api_url,
      api_key: model.api_key,
      temperature: model.temperature || 0.7,
    });
    setEditingModelId(model.id);
    setAddModelMode(true);
  };

  const cancelEditModel = () => {
    setEditingModelId(null);
    setAddModelMode(false);
    resetModelForm();
  };

  const editCustomModel = async () => {
    if (!modelFormData.model_name?.trim())
      return toast.error("Enter model name.");
    if (!modelFormData.api_url?.trim()) return toast.error("Enter API URL.");
    if (!modelFormData.api_key?.trim()) return toast.error("Enter API key.");

    setSavingModel(true);
    try {
      const api = await axiosAuth();
      await api.put(`/models/${editingModelId}`, {
        model_name: modelFormData.model_name,
        provider: modelFormData.provider,
        api_url: modelFormData.api_url,
        api_key: modelFormData.api_key,
        temperature: modelFormData.temperature,
      });

      toast.success("Custom model updated!");
      setEditingModelId(null);
      setAddModelMode(false);
      resetModelForm();
      await fetchAvailableModels();
    } catch (err) {
      console.error("Edit model error", err);
      toast.error(extractErrorMessage(err, "Failed to update model."));
    } finally {
      setSavingModel(false);
    }
  };

  const signOut = async () => {
    _sessionToken = null; // clear frontend cache
    _sessionExpiry = 0;
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
    setFastHistory([]);
    setActivePdfUrl("");
    setActivePdfName("");
    setCollectionFiles([]);
    setShowDashboard(false);
    setShowPdfViewer(false);
    setChatAnalytics({});
    setMode("chat");

    // reset model selection state
    setSelectedModel(null);
    setModelSelectionOpen(false);
    setAvailableModels([]);
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

  const renameCollection = async (targetId) => {
    const id = targetId || collectionId;
    if (!id) return toast.error("Select a collection first.");
    if (!renameValue?.trim()) return toast.error("Enter a name.");

    try {
      const api = await axiosAuth();
      await api.post(`/collections/${id}/rename`, {
        name: renameValue.trim(),
      });
      await fetchCollections();
      toast.success("Collection renamed");
      setRenameModalOpen(false);
      setRenameTarget(null);
      setRenameValue("");
    } catch (err) {
      console.log(err);
      toast.error("Rename failed.");
    }
  };

  const deleteCollection = async (targetId) => {
    const id = targetId || collectionId;
    if (!id) return toast.error("Select a collection first.");

    setDeletingCollection(true);
    const toastId = toast.loading("Deleting collection...");

    try {
      const api = await axiosAuth();
      await api.delete(`/collections/${id}`);

      // Close modal immediately
      setDeleteModalOpen(false);
      setDeleteTarget(null);

      if (collectionId === id) {
        setCollectionId("");
        setAskRes(null);
        setUploadRes(null);
        setChatMessages([]);
        setFastHistory([]);
        setCollectionFiles([]);
        setShowDocBar(false);
        setActivePdfUrl("");
        setActivePdfName("");
        setShowDashboard(false);
        setShowPdfViewer(false);
      }

      await fetchCollections();
      toast.success("Collection deleted", { id: toastId });
    } catch (err) {
      console.error(err);
      toast.error("Delete failed. Please try again.", { id: toastId });
      // Always close modal and refresh — server may have succeeded
      setDeleteModalOpen(false);
      setDeleteTarget(null);
      await fetchCollections();
    } finally {
      setDeletingCollection(false);
    }
  };

  // --------------------------------
  // API: Upload
  // --------------------------------
  const uploadMultiPDF = async () => {
    if (!files.length) return toast.error("Select at least 1 PDF.");
    if (!user) return toast.error("Login first.");

    setUploading(true);
    setUploadRes(null);
    setAskRes(null);
    setShowDashboard(false);
    setUploadProgress(0);

    // Start elapsed timer
    setUploadElapsed(0);
    uploadTimerRef.current = setInterval(
      () => setUploadElapsed((t) => t + 1),
      1000,
    );

    const uploadToastId = toast.loading("Uploading & indexing PDFs...");

    try {
      const api = await axiosAuth();
      const formData = new FormData();
      files.forEach((f) => formData.append("files", f));
      // Only append collection_id when adding to existing (paperclip), not when creating a new chat ("+")
      if (collectionId && !forceNewCollection)
        formData.append("collection_id", collectionId);
      formData.append("index_type", indexType);

      const res = await api.post(`/upload-multi`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => {
          if (e.total)
            setUploadProgress(Math.round((e.loaded * 100) / e.total));
        },
      });

      setUploadRes(res.data);
      setCollectionId(res.data.collection_id);

      await fetchCollections();

      toast.success(
        `Upload complete — ${res.data.pages_loaded ?? ""} pages indexed (${indexType === "tree" ? "Tree" : "Vector"})`,
        { id: uploadToastId },
      );
      setShowUploadModal(false);
      setFiles([]);
      setForceNewCollection(false);
      setIndexType("vector");
    } catch (err) {
      console.log(err);
      toast.error("Upload failed. Check backend + auth.", {
        id: uploadToastId,
      });
    } finally {
      setUploading(false);
      clearInterval(uploadTimerRef.current);
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
        toast.error("No PDFs found in this collection.");
        return;
      }

      const targetFile = fileId
        ? collectionFiles.find((f) => f.id === fileId)
        : collectionFiles[0];

      if (!targetFile) {
        toast.error("File not found.");
        return;
      }

      const api = await axiosAuth();
      const res = await api.get(
        `/collections/${collectionId}/files/${targetFile.id}/signed-url`,
      );

      const signedUrl = res.data?.signed_url;
      const filename = res.data?.filename || targetFile.filename || "PDF";

      if (!signedUrl) {
        toast.error("Signed URL not received.");
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
      toast.error("Could not open PDF viewer.");
    }
  };

  // --------------------------------
  // API: Chat
  // --------------------------------
  const fetchChat = async () => {
    if (!collectionId) return;
    // Show cached messages instantly while a fresh fetch is pending
    if (chatCache[collectionId]) {
      setChatMessages(chatCache[collectionId]);
    }
    try {
      const api = await axiosAuth();
      const res = await api.get(`/collections/${collectionId}/chat`);
      const msgs = res.data.messages || [];
      setChatMessages(msgs);
      setChatCache((prev) => ({ ...prev, [collectionId]: msgs }));
    } catch (err) {
      console.log("chat fetch error", err);
      if (!chatCache[collectionId]) setChatMessages([]);
    }
  };

  const fetchFastHistory = async (cid) => {
    const id = cid || collectionId;
    if (!id) return;
    try {
      const api = await axiosAuth();
      const res = await api.get(`/collections/${id}/ask-history`);
      setFastHistory(res.data.history || []);
    } catch (err) {
      console.log("fast history fetch error", err);
      setFastHistory([]);
    }
  };

  const clearChat = async () => {
    if (!collectionId) return toast.error("Select a collection first.");

    try {
      const api = await axiosAuth();
      await api.delete(`/collections/${collectionId}/chat`);
      setChatMessages([]);
      setAskRes(null);
      setShowDashboard(false);
      setClearChatModalOpen(false);
      toast.success("Chat cleared");
    } catch (err) {
      console.log(err);
      toast.error("Clear chat failed.");
    }
  };

  const sendChatMessage = async () => {
    if (!collectionId) return toast.error("Select a collection first.");
    setChatLoading(true);
    setQueryElapsed(0);
    queryTimerRef.current = setInterval(
      () => setQueryElapsed((t) => t + 1),
      1000,
    );

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
      const token = await getCachedSession();
      if (!token) throw new Error("No active session.");

      const res = await fetch(`${API}/chat-stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          question: userMsg,
          collection_id: collectionId,
          model_name: selectedModel,
        }),
      });

      if (!res.ok) {
        if (res.status === 401) {
          _sessionToken = null;
          _sessionExpiry = 0;
        }
        throw new Error(`Streaming failed (${res.status}).`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let assistantText = "";
      let msgIndex = -1;

      // track the index of the assistant placeholder we just pushed
      setChatMessages((prev) => {
        msgIndex = prev.length - 1;
        return prev;
      });

      while (true) {
        let value, done;
        try {
          ({ value, done } = await reader.read());
        } catch (_readErr) {
          // ERR_INCOMPLETE_CHUNKED_ENCODING — stream cut short, show what we have
          break;
        }
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        assistantText += chunk;

        // Strip any partial __META__ suffix while streaming so it doesn't flash
        const displayText = assistantText.includes("__META__")
          ? assistantText.split("\n\n__META__")[0]
          : assistantText;

        setChatMessages((prev) => {
          const updated = [...prev];
          for (let i = updated.length - 1; i >= 0; i--) {
            if (updated[i].role === "assistant") {
              updated[i] = { ...updated[i], message: displayText };
              break;
            }
          }
          return updated;
        });
      }

      // Parse metadata trailer if present
      const metaSplit = assistantText.split("\n\n__META__");
      if (metaSplit.length === 2) {
        try {
          const meta = JSON.parse(metaSplit[1].trim());
          setChatAnalytics((prev) => ({ ...prev, [msgIndex]: meta }));
        } catch (_) {
          // ignore parse errors
        }
      }

      fetchLeaderboard();
      // Chat messages already updated via streaming state — no need to re-fetch
    } catch (err) {
      console.log(err);
      toast.error("Chat failed.");
      setChatMessages((prev) => prev.slice(0, -2));
    } finally {
      setChatLoading(false);
      clearInterval(queryTimerRef.current);
    }
  };
  const askQuestion = async () => {
    if (!question.trim()) return toast.error("Enter a question.");
    if (!collectionId) return toast.error("Select a collection first.");
    if (mode === "chat")
      return toast.error("Chat mode uses streaming endpoint, not /ask");

    const pendingQ = question.trim();
    setQuestion(""); // clear textarea immediately — like chat mode
    setPendingQuestion(pendingQ); // keep text visible in the skeleton bubble

    setAsking(true);
    setAskRes(null);
    setShowDashboard(false);
    setQueryElapsed(0);
    queryTimerRef.current = setInterval(
      () => setQueryElapsed((t) => t + 1),
      1000,
    );

    try {
      const api = await axiosAuth();

      const payload = {
        question: pendingQ,
        collection_id: collectionId,
        mode,
        model_name: selectedModel,
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
      setLastQueryResult(res.data); // Persist query result for PDF when navigating away
      setLastQueryTimestamp(new Date()); // Track when query was executed
      setShowDashboard(true); // ✅ auto open after ask
      setIndexMissing(false); // Reset on success
      // Optimistically append to history thread
      setFastHistory((prev) => [
        ...prev,
        {
          id: `local-${Date.now()}`,
          question: res.data.question || pendingQ,
          answer: res.data.final_answer,
          best_pipeline: res.data.best_pipeline,
          mode,
          created_at: new Date().toISOString(),
          metrics: res.data.metrics,
          retrieval_comparison: res.data.retrieval_comparison,
        },
      ]);
      // Confirm with a server refresh in the background
      fetchFastHistory();
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
        toast.error("⚠️ Collection exists but local index is missing.");
        setIndexMissing(true);
      } else if (errorDetail === "Invalid collection_id. Upload first.") {
        toast.error("⚠️ No PDFs in this collection. Please upload PDFs first.");
        setIndexMissing(false);
      } else if (errorDetail) {
        toast.error("Ask failed: " + JSON.stringify(errorDetail));
        setIndexMissing(false);
      } else if (err.response?.data) {
        toast.error("Ask failed: " + JSON.stringify(err.response.data));
        setIndexMissing(false);
      } else {
        toast.error("Ask failed. Check backend logs.");
        setIndexMissing(false);
      }
    } finally {
      setAsking(false);
      setPendingQuestion(""); // clear after answer lands (or on error)
      clearInterval(queryTimerRef.current);
    }
  };

  const rebuildIndex = async () => {
    if (!collectionId) return;

    setRebuildingIndex(true);
    const rebuildToastId = toast.loading("Rebuilding index...");
    try {
      const api = await axiosAuth();
      const res = await api.post(`/collections/${collectionId}/rebuild-index`);

      let successMsg = `Index rebuilt! ${res.data.chunks_created} chunks in ${res.data.time_taken_sec}s`;
      if (res.data.failed_files && res.data.failed_files.length > 0) {
        successMsg += ` (⚠️ ${res.data.failed_files.length} files failed)`;
      }

      toast.success(successMsg, { id: rebuildToastId, duration: 5000 });
      setIndexMissing(false);
    } catch (err) {
      console.log("❌ Rebuild error:", err);
      console.log("❌ Rebuild error response:", err.response);

      const errorDetail =
        err.response?.data?.detail || err.message || "Unknown error";
      toast.error(`Failed to rebuild index: ${errorDetail}`, {
        id: rebuildToastId,
      });
    } finally {
      setRebuildingIndex(false);
    }
  };

  const handleImageTest = async () => {
    if (!imgFile) return toast.error("Please select an image first.");
    if (!imgQuestion.trim() && !question.trim())
      return toast.error("Enter a question about the image.");

    const q = imgQuestion.trim() || question.trim();
    setImgLoading(true);
    setImgRes(null);

    const imgToastId = toast.loading("Analyzing image...");

    try {
      const api = await axiosAuth();
      const fd = new FormData();
      fd.append("image", imgFile);
      fd.append("question", q);
      if (collectionId) fd.append("collection_id", collectionId);
      if (selectedModel) fd.append("model_name", selectedModel);

      const res = await api.post("/image-test", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      setImgRes(res.data);
      if (res.data.failure_type) {
        toast.error(`Image analyzed with issue: ${res.data.failure_type}`, {
          id: imgToastId,
          duration: 4000,
        });
      } else {
        toast.success("Image analyzed successfully", { id: imgToastId });
      }
    } catch (err) {
      console.error("Image test error:", err);
      toast.error(
        err.response?.data?.detail || "Image test failed. Check backend logs.",
        { id: imgToastId },
      );
    } finally {
      setImgLoading(false);
    }
  };

  const handleUnifiedQuery = async () => {
    if (!user) return toast.error("Login first.");
    if (mode === "image") return handleImageTest();
    if (!question.trim()) return toast.error("Enter a question.");
    if (!collectionId) return toast.error("Upload/select a collection first.");

    setShowAllPipelines(false);
    if (mode === "chat") await sendChatMessage();
    else await askQuestion();
  };

  // --------------------------------
  // Leaderboard
  // --------------------------------
  const fetchLeaderboard = async () => {
    setLeaderboardLoading(true);
    try {
      const api = await axiosAuth();
      const res = await api.get(`/leaderboard/global`, {
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

  // Helper: Get active query data (current or cached)
  const getActiveQueryData = () => {
    return askRes || lastQueryResult;
  };

  // Helper: Get query freshness label
  const getQueryFreshnessLabel = () => {
    if (askRes) return "Current Query";
    if (lastQueryResult && lastQueryTimestamp) {
      const mins = Math.floor((Date.now() - lastQueryTimestamp) / 60000);
      if (mins < 1) return "Last Query (just now)";
      if (mins < 60) return `Last Query (${mins} min ago)`;
      const hours = Math.floor(mins / 60);
      if (hours < 24) return `Last Query (${hours}h ago)`;
      return `Last Query (${Math.floor(hours / 24)}d ago)`;
    }
    return null;
  };

  const downloadAnalyticsPDF = async () => {
    try {
      if (!leaderboard) {
        toast.error("No analytics data available");
        return;
      }

      const pdf = new jsPDF("p", "mm", "a4");
      const timestamp = new Date().toLocaleString();
      const queryData = getActiveQueryData(); // Use helper to get query data
      const safeMetrics = queryData?.metrics || {};
      let yPos = 15;
      let pageBreakThreshold = 270;

      const addPageIfNeeded = () => {
        if (yPos > pageBreakThreshold) {
          pdf.addPage();
          yPos = 15;
          return true;
        }
        return false;
      };

      // ═══════════════════════════════════════════════════════════
      // SECTION 1: REPORT HEADER
      // ═══════════════════════════════════════════════════════════
      pdf.setFontSize(20);
      pdf.setFont(undefined, "bold");
      pdf.text("RAG Analytics Report", 15, yPos);
      yPos += 12;

      pdf.setFontSize(10);
      pdf.setFont(undefined, "normal");
      pdf.setTextColor(100);
      pdf.text(`Generated: ${timestamp}`, 15, yPos);
      yPos += 6;
      pdf.text(`Collection: ${activeCollectionName || "N/A"}`, 15, yPos);
      yPos += 6;
      pdf.text(
        `Index Type: ${activeCollectionIndexType === "tree" ? "Page Index (Tree)" : "Vector Database"}`,
        15,
        yPos,
      );
      yPos += 10;
      pdf.setTextColor(0);

      // ═══════════════════════════════════════════════════════════
      // SECTION 2: QUERY ANALYSIS (current or cached)
      // ═══════════════════════════════════════════════════════════
      const queryFreshnessLabel = getQueryFreshnessLabel();
      if (queryData) {
        addPageIfNeeded();
        pdf.setFontSize(14);
        pdf.setFont(undefined, "bold");
        pdf.text(
          queryFreshnessLabel
            ? `${queryFreshnessLabel} Analysis`
            : "Query Analysis",
          15,
          yPos,
        );
        yPos += 10;

        // Question & Answer
        pdf.setFontSize(10);
        pdf.setFont(undefined, "bold");
        pdf.text("Question:", 15, yPos);
        yPos += 6;
        pdf.setFont(undefined, "normal");
        const questionLines = pdf.splitTextToSize(
          queryData.question || "N/A",
          180,
        );
        pdf.text(questionLines, 15, yPos);
        yPos += questionLines.length * 5 + 4;

        pdf.setFont(undefined, "bold");
        pdf.text("Final Answer:", 15, yPos);
        yPos += 6;
        pdf.setFont(undefined, "normal");
        const answerLines = pdf.splitTextToSize(
          queryData.final_answer || "N/A",
          180,
        );
        pdf.text(answerLines, 15, yPos);
        yPos += Math.min(answerLines.length * 4, 40) + 4;

        addPageIfNeeded();

        pdf.setFont(undefined, "bold");
        pdf.text("Best Pipeline:", 15, yPos);
        yPos += 6;
        pdf.setFont(undefined, "normal");
        pdf.text(queryData.best_pipeline || "N/A", 15, yPos);
        yPos += 8;

        // Performance Metrics (Current Query)
        pdf.setFont(undefined, "bold");
        pdf.text("Performance Metrics:", 15, yPos);
        yPos += 6;
        pdf.setFont(undefined, "normal");
        pdf.setFontSize(9);

        const perfMetrics = [
          [
            `Total Latency: ${fmtMs(safeMetrics?.timings_ms?.total_ms || 0)}`,
            `Embedding: ${fmtMs(safeMetrics?.timings_ms?.embedding_ms || 0)}`,
          ],
          [
            `Retrieval: ${fmtMs(safeMetrics?.timings_ms?.retrieval_ms || 0)}`,
            `Rerank: ${fmtMs(safeMetrics?.timings_ms?.rerank_ms || 0)}`,
          ],
          [
            `LLM: ${fmtMs(safeMetrics?.timings_ms?.llm_ms || 0)}`,
            `Smart Extract: ${fmtMs(safeMetrics?.timings_ms?.smart_extract_ms || 0)}`,
          ],
        ];

        perfMetrics.forEach((row) => {
          pdf.text(`${row[0]} | ${row[1]}`, 15, yPos);
          yPos += 5;
        });

        // Tokens & Cost
        yPos += 3;
        pdf.setFont(undefined, "bold");
        pdf.text("Tokens & Cost:", 15, yPos);
        yPos += 5;
        pdf.setFont(undefined, "normal");

        const tokenMetrics = [
          [
            `Prompt Tokens: ${fmtNum(safeMetrics?.tokens?.prompt_tokens || 0)}`,
            `Completion Tokens: ${fmtNum(safeMetrics?.tokens?.completion_tokens || 0)}`,
          ],
          [
            `Total Tokens: ${fmtNum(safeMetrics?.tokens?.total_tokens || 0)}`,
            `Cost: ${fmtMoney(safeMetrics?.cost_usd || 0)}`,
          ],
          [
            `Model: ${safeMetrics?.tokens?.model || "N/A"}`,
            `Cache Hit: ${String(safeMetrics?.cache_hit ?? false)}`,
          ],
        ];

        tokenMetrics.forEach((row) => {
          pdf.text(`${row[0]} | ${row[1]}`, 15, yPos);
          yPos += 5;
        });

        yPos += 4;
      }

      // ═══════════════════════════════════════════════════════════
      // SECTION 3: PIPELINE COMPARISON TABLE
      // ═══════════════════════════════════════════════════════════
      if (
        queryData?.retrieval_comparison &&
        queryData.retrieval_comparison.length > 0
      ) {
        addPageIfNeeded();
        pdf.setFontSize(14);
        pdf.setFont(undefined, "bold");
        pdf.text("Pipeline Comparison", 15, yPos);
        yPos += 10;

        pdf.setFont(undefined, "normal");
        pdf.setFontSize(8);

        // Draw table header
        const tableStartY = yPos;
        const colWidths = [10, 35, 20, 20, 20, 20, 25];
        const headers = [
          "#",
          "Pipeline",
          "Relevance",
          "Grounded",
          "Quality",
          "Efficiency",
          "Final Score",
        ];
        let colX = 15;

        pdf.setFont(undefined, "bold");
        pdf.setFillColor(174, 86, 48);
        pdf.setTextColor(255);
        headers.forEach((header, i) => {
          pdf.rect(colX, yPos, colWidths[i], 7, "F");
          pdf.text(header, colX + 1, yPos + 5);
          colX += colWidths[i];
        });

        yPos += 7;
        pdf.setTextColor(0);
        pdf.setFont(undefined, "normal");

        // Draw table rows
        queryData.retrieval_comparison.slice(0, 5).forEach((p, idx) => {
          const rowData = [
            String(idx + 1),
            p.pipeline.substring(0, 20),
            `${(p.scores?.relevance ?? 0).toFixed(2)}`,
            `${(p.scores?.grounded ?? 0).toFixed(2)}`,
            `${(p.scores?.quality ?? 0).toFixed(2)}`,
            `${(p.scores?.efficiency ?? 0).toFixed(2)}`,
            `${(p.scores?.final ?? 0).toFixed(2)}`,
          ];

          colX = 15;
          rowData.forEach((cell, i) => {
            pdf.rect(colX, yPos, colWidths[i], 6);
            pdf.text(cell, colX + 1, yPos + 4);
            colX += colWidths[i];
          });
          yPos += 6;

          if (yPos > pageBreakThreshold) {
            pdf.addPage();
            yPos = 15;
          }
        });

        yPos += 4;
      }

      // ═══════════════════════════════════════════════════════════
      // SECTION 3.5: PIPELINE CONFIGURATIONS & CONTEXT
      // ═══════════════════════════════════════════════════════════
      if (
        queryData?.retrieval_comparison &&
        queryData.retrieval_comparison.length > 0
      ) {
        addPageIfNeeded();
        pdf.setFontSize(14);
        pdf.setFont(undefined, "bold");
        pdf.text("Pipeline Configurations & Context Snippets", 15, yPos);
        yPos += 10;

        pdf.setFont(undefined, "normal");
        pdf.setFontSize(9);

        queryData.retrieval_comparison.slice(0, 4).forEach((p, idx) => {
          if (idx > 0) yPos += 6;
          pdf.setFont(undefined, "bold");
          pdf.text(`${idx + 1}. ${p.pipeline}`, 15, yPos);
          yPos += 5;

          pdf.setFont(undefined, "normal");
          const configDetails = `Chunk Size: ${p.chunk_size || "N/A"} | Overlap: ${p.overlap || "N/A"} | Top-K: ${p.top_k || "N/A"} | Search: ${p.search_type || "N/A"}`;
          pdf.text(configDetails, 20, yPos);
          yPos += 5;

          if (p.context_preview) {
            const previewLines = pdf.splitTextToSize(
              `Context: ${p.context_preview.replace(/\\n/g, " ")}`,
              170,
            );
            const linesToPrint = previewLines.slice(0, 3);
            pdf.text(linesToPrint, 20, yPos);
            yPos += linesToPrint.length * 4 + 2;
          }

          addPageIfNeeded();
        });
        yPos += 4;
      }

      // ═══════════════════════════════════════════════════════════
      // SECTION 4: PER-PIPELINE DETAILED REPORT
      // ═══════════════════════════════════════════════════════════
      if (
        queryData?.metrics?.pipeline_latencies &&
        queryData.metrics.pipeline_latencies.length > 0
      ) {
        addPageIfNeeded();
        pdf.setFontSize(14);
        pdf.setFont(undefined, "bold");
        pdf.text("Per-Pipeline Latency Breakdown", 15, yPos);
        yPos += 10;

        pdf.setFont(undefined, "normal");
        pdf.setFontSize(9);

        queryData.metrics.pipeline_latencies.slice(0, 4).forEach((pl, idx) => {
          if (idx > 0) yPos += 8;

          pdf.setFont(undefined, "bold");
          pdf.text(`${idx + 1}. ${pl.pipeline}`, 15, yPos);
          yPos += 6;

          pdf.setFont(undefined, "normal");
          const pipelineDetails = [
            `Retrieval: ${fmtMs(pl.retrieval_ms)} | Context Build: ${fmtMs(pl.context_build_ms)}`,
            `Scoring: ${fmtMs(pl.scoring_ms)} | Total: ${fmtMs(pl.total_ms)}`,
          ];

          pipelineDetails.forEach((text) => {
            pdf.text(text, 20, yPos);
            yPos += 5;
          });

          addPageIfNeeded();
        });

        yPos += 4;
      }

      // ═══════════════════════════════════════════════════════════
      // SECTION 5: GLOBAL LEADERBOARD (Top Performers)
      // ═══════════════════════════════════════════════════════════
      addPageIfNeeded();
      pdf.setFontSize(14);
      pdf.setFont(undefined, "bold");
      pdf.text("Global Leaderboard - Top Performers", 15, yPos);
      yPos += 10;

      pdf.setFont(undefined, "normal");
      pdf.setFontSize(9);

      pdf.text(
        `Total Questions Analyzed: ${leaderboard.total_questions}`,
        15,
        yPos,
      );
      yPos += 6;
      pdf.text(
        `Best Pipeline Today: ${leaderboard.best_pipeline_today || "N/A"}`,
        15,
        yPos,
      );
      yPos += 10;

      if (leaderboard.pipelines && leaderboard.pipelines.length > 0) {
        pdf.setFontSize(8);
        const colWidths = [12, 45, 22, 15, 18, 28];
        const headers = [
          "Rank",
          "Pipeline",
          "Score",
          "Wins",
          "Win Rate",
          "Avg Retrieval",
        ];
        let colX = 15;

        // Draw table header
        pdf.setFont(undefined, "bold");
        pdf.setFillColor(174, 86, 48);
        pdf.setTextColor(255);
        headers.forEach((header, i) => {
          pdf.rect(colX, yPos, colWidths[i], 7, "F");
          pdf.text(header, colX + 1, yPos + 5);
          colX += colWidths[i];
        });

        yPos += 7;
        pdf.setTextColor(0);
        pdf.setFont(undefined, "normal");

        // Draw table rows
        leaderboard.pipelines.slice(0, 10).forEach((p, idx) => {
          const scoreDisplay =
            p.leaderboard_score != null
              ? `${(p.leaderboard_score * 100).toFixed(1)}%`
              : p.avg_final_score.toFixed(3);
          const avgRetrievalMs =
            p.avg_retrieval_ms ||
            (p.avg_retrieval_time_sec * 1000).toFixed(0) ||
            "N/A";

          const rowData = [
            String(idx + 1),
            p.pipeline.substring(0, 30),
            scoreDisplay,
            String(p.wins),
            `${(p.win_rate * 100).toFixed(1)}%`,
            typeof avgRetrievalMs === "string"
              ? avgRetrievalMs
              : `${avgRetrievalMs}ms`,
          ];

          colX = 15;
          rowData.forEach((cell, i) => {
            pdf.rect(colX, yPos, colWidths[i], 6);
            pdf.text(cell, colX + 1, yPos + 4);
            colX += colWidths[i];
          });
          yPos += 6;

          if (yPos > pageBreakThreshold) {
            pdf.addPage();
            yPos = 15;
          }
        });

        yPos += 4;
      }

      // ═══════════════════════════════════════════════════════════
      // SECTION 6: SUMMARY & KEY INSIGHTS
      // ═══════════════════════════════════════════════════════════
      addPageIfNeeded();
      pdf.setFontSize(14);
      pdf.setFont(undefined, "bold");
      pdf.text("Summary & Key Insights", 15, yPos);
      yPos += 10;

      pdf.setFont(undefined, "normal");
      pdf.setFontSize(10);

      const insights = [];
      if (leaderboard.pipelines && leaderboard.pipelines.length > 0) {
        const topPipeline = leaderboard.pipelines[0];
        const avgScore = (
          leaderboard.pipelines.reduce(
            (sum, p) => sum + (p.avg_final_score || 0),
            0,
          ) / leaderboard.pipelines.length
        ).toFixed(3);
        insights.push(
          `• Top Performer: ${topPipeline.pipeline} with score ${topPipeline.avg_final_score?.toFixed(3) || "N/A"}`,
        );
        insights.push(`• Average Pipeline Score: ${avgScore}`);
        insights.push(
          `• Total Evaluation Count: ${leaderboard.total_questions} questions`,
        );
      }

      if (queryData?.best_pipeline) {
        const metric = queryData?.metrics?.timings_ms?.total_ms
          ? fmtMs(queryData.metrics.timings_ms.total_ms)
          : "N/A";
        insights.push(``);
        const queryLabel = getQueryFreshnessLabel() || "Query";
        insights.push(`• ${queryLabel} Best: ${queryData.best_pipeline}`);
        insights.push(`  Total Latency: ${metric}`);
      }

      insights.push(`• Report Generated: ${timestamp}`);

      insights.forEach((insight) => {
        const lines = pdf.splitTextToSize(insight, 170);
        pdf.text(lines, 15, yPos);
        yPos += lines.length * 5 + 3;
        addPageIfNeeded();
      });

      // Download the PDF
      const filename = `RAG_Analytics_${Date.now()}.pdf`;
      pdf.save(filename);
      toast.success("Comprehensive analytics PDF downloaded");
    } catch (error) {
      console.error("PDF download error:", error);
      toast.error("Failed to download PDF");
    }
  };

  const downloadReportViaApi = async (reportFormat) => {
    if (!askRes?.retrieval_comparison || mode === "chat") {
      toast.error("No compare data available. Use Fast/Compare mode first.");
      return;
    }

    setDownloadingReport(true);
    try {
      const api = await axiosAuth();
      const res = await api.post(
        "/export/compare-report",
        {
          format: reportFormat,
          payload: buildBaseReportData(),
        },
        { responseType: "blob" },
      );

      const mime = res.headers["content-type"] || "application/octet-stream";
      const timestamp = Date.now();
      const ext = reportFormat.toLowerCase();
      const filename = `RAG_Report_${safeFileName(collectionId?.slice(0, 8))}_${timestamp}.${ext}`;
      downloadBlob(res.data, filename, mime);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (detail) toast.error(String(detail));
      else toast.error("Report export failed.");
    } finally {
      setDownloadingReport(false);
    }
  };

  const applyPipelinePreset = async (presetKey) => {
    if (!collectionId) return toast.error("Select a collection first.");
    setPresetApplying(true);
    try {
      const api = await axiosAuth();
      await api.post(`/collections/${collectionId}/apply-preset`, {
        preset_key: presetKey,
      });
      toast.success(`Applied ${presetKey} preset`);
      fetchCustomPipeline();
    } catch {
      toast.error("Failed to apply preset.");
    } finally {
      setPresetApplying(false);
    }
  };

  // --------------------------------
  // Chunk Explorer
  // --------------------------------
  const fetchChunks = async () => {
    if (!collectionId) return;
    setChunksLoading(true);

    try {
      const api = await axiosAuth();
      const params = {
        q: chunkQuery || undefined,
        pipeline: chunkFilterPipeline || undefined,
        file_id: chunkFilterFileId || undefined,
        page: chunkFilterPage ? parseInt(chunkFilterPage, 10) : undefined,
        limit: chunkLimit,
        offset: chunkOffset,
      };

      const res = await api.get(`/collections/${collectionId}/chunks`, {
        params,
      });
      const loadedChunks = res.data.chunks || [];
      setChunks(loadedChunks);
      setChunksTotal(res.data.total || 0);
      // Collect unique pipeline names seen so far for dropdown suggestions
      const newNames = loadedChunks.map((c) => c.pipeline_name).filter(Boolean);
      if (newNames.length) {
        setKnownPipelines((prev) => {
          const merged = Array.from(new Set([...prev, ...newNames])).sort();
          return merged;
        });
      }
    } catch (e) {
      console.log("Chunk fetch error:", e);
      setChunks([]);
      setChunksTotal(0);
      toast.error("Failed to load chunks.");
    } finally {
      setChunksLoading(false);
    }
  };

  const collectInitialExpanded = (node, depth = 0, acc = {}) => {
    if (!node || typeof node !== "object") return acc;
    if (node.id) acc[node.id] = depth < 2;
    const children = Array.isArray(node.children) ? node.children : [];
    children.forEach((child) => collectInitialExpanded(child, depth + 1, acc));
    return acc;
  };

  const fetchTreeIndex = async () => {
    if (!collectionId) return;
    setTreeLoading(true);
    setTreeError("");

    try {
      const api = await axiosAuth();
      const res = await api.get(`/page-index/tree/${collectionId}`);
      const tree = res.data?.tree || null;
      setTreeData(tree);
      setTreeExpanded(collectInitialExpanded(tree));
    } catch (e) {
      setTreeData(null);
      const msg = e.response?.data?.detail || "Failed to load tree index.";
      setTreeError(msg);
      toast.error(msg);
    } finally {
      setTreeLoading(false);
    }
  };

  // Auto-fetch chunks when offset changes
  useEffect(() => {
    if (chunkExplorerOpen && collectionId) {
      if (activeCollectionIndexType !== "tree") {
        fetchChunks();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chunkOffset, activeCollectionIndexType]);

  // Auto-load all chunks when the explorer is first opened
  useEffect(() => {
    if (chunkExplorerOpen && collectionId) {
      setKnownPipelines([]); // reset per-collection
      setChunkOffset(0);
      if (activeCollectionIndexType !== "tree") {
        fetchChunks();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chunkExplorerOpen, activeCollectionIndexType]);

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
      toast.error("No compare data available. Use Fast/Compare mode first.");
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
      toast.error("TXT report download failed.");
    } finally {
      setDownloadingReport(false);
    }
  };

  // --------------------------------
  // Export JSON
  // --------------------------------
  const downloadReportJSON = () => {
    if (!askRes?.retrieval_comparison || mode === "chat") {
      toast.error("No comparison data available. Use Fast/Compare mode first.");
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
      toast.error("No comparison data available. Use Fast/Compare mode first.");
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
  const pipelineData = useMemo(
    () => askRes?.retrieval_comparison ?? [],
    [askRes],
  );

  const labels = useMemo(
    () => pipelineData.map((p) => shortLabel(p.pipeline)),
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
        borderWidth: 1,
        borderColor: "rgba(0,0,0,0.1)",
      },
    ],
  };

  const scoreChart = {
    labels,
    datasets: [
      {
        label: "Relevance (0-10)",
        data: relevanceScores,
        borderWidth: 1,
        borderColor: "rgba(0,0,0,0.1)",
      },
      {
        label: "Grounded (0-10)",
        data: groundedScores,
        borderWidth: 1,
        borderColor: "rgba(0,0,0,0.1)",
      },
    ],
  };

  const qualityEfficiencyChart = {
    labels,
    datasets: [
      {
        label: "Quality (0-10)",
        data: qualityScores,
        borderWidth: 1,
        borderColor: "rgba(0,0,0,0.1)",
      },
      {
        label: "Efficiency (0-10)",
        data: efficiencyScores,
        borderWidth: 1,
        borderColor: "rgba(0,0,0,0.1)",
      },
    ],
  };

  const finalScoreChart = {
    labels,
    datasets: [
      {
        label: "Final Score (0-10)",
        data: finalScores,
        borderWidth: 1,
        borderColor: "rgba(0,0,0,0.1)",
      },
    ],
  };

  // Brutalist chart options (Claude palette) — memoized on darkMode + pipelineData
  const brutalistChartOptions = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      plugins: {
        legend: {
          display: true,
          labels: {
            color: darkMode ? "#eee" : "#333",
            font: { weight: "600", size: 11, family: "Georgia, serif" },
            boxWidth: 12,
            boxHeight: 12,
            padding: 10,
          },
        },
        tooltip: {
          enabled: true,
          backgroundColor: darkMode ? "#393937" : "#fff",
          titleColor: darkMode ? "#eee" : "#333",
          bodyColor: darkMode ? "#eee" : "#333",
          borderColor: darkMode ? "rgba(108,106,96,0.3)" : "rgba(0,0,0,0.1)",
          borderWidth: 1,
          titleFont: { weight: "600", size: 12, family: "Georgia, serif" },
          bodyFont: { weight: "500", size: 12, family: "Georgia, serif" },
          padding: 10,
          cornerRadius: 8,
          displayColors: true,
          boxPadding: 4,
          callbacks: {
            title: (items) => {
              // Show full pipeline name in tooltip even when axis shows short label
              const idx = items[0]?.dataIndex;
              return idx !== undefined && pipelineData[idx]
                ? pipelineData[idx].pipeline
                : "";
            },
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
            color: darkMode ? "#9a9893" : "#6b6a68",
            font: { weight: "500", size: 11 },
          },
          grid: {
            color: darkMode ? "rgba(108,106,96,0.15)" : "rgba(0,0,0,0.06)",
            lineWidth: 1,
          },
          border: {
            color: darkMode ? "rgba(108,106,96,0.3)" : "rgba(0,0,0,0.1)",
            width: 1,
          },
        },
        y: {
          beginAtZero: true,
          ticks: {
            color: darkMode ? "#9a9893" : "#6b6a68",
            font: { weight: "500", size: 11 },
          },
          grid: {
            color: darkMode ? "rgba(108,106,96,0.15)" : "rgba(0,0,0,0.06)",
            lineWidth: 1,
          },
          border: {
            color: darkMode ? "rgba(108,106,96,0.3)" : "rgba(0,0,0,0.1)",
            width: 1,
          },
        },
      },
    }),
    [darkMode, pipelineData],
  );
  const brutalistColors = [
    "#ae5630", // accent
    "#d4764a", // lighter accent
    "#DDD9CE", // beige
    "#9a9893", // muted
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
  const latencyLabels = [
    "Embedding",
    "Retrieval",
    "Rerank",
    "LLM",
    "Smart Extract",
  ];
  const latencyValues = [
    timings.embedding_ms ?? 0,
    timings.retrieval_ms ?? 0,
    timings.rerank_ms ?? 0,
    timings.llm_ms ?? 0,
    timings.smart_extract_ms ?? 0,
  ];

  const latencyChart = {
    labels: latencyLabels,
    datasets: [
      {
        label: "Latency (ms)",
        data: latencyValues,
        borderColor: brutalistColors[0],
        borderWidth: 1,
        borderRadius: 6,
        backgroundColor: brutalistColors[1],
      },
    ],
  };

  // Update chart datasets with Claude styling
  retrievalChart.datasets[0].backgroundColor = pipelineData.map(
    (_, i) => brutalistColors[i % brutalistColors.length],
  );
  retrievalChart.datasets[0].borderColor = pipelineData.map(
    (_, i) => brutalistColors[i % brutalistColors.length],
  );
  retrievalChart.datasets[0].borderWidth = 1;
  retrievalChart.datasets[0].borderRadius = 6;

  scoreChart.datasets[0].backgroundColor = brutalistColors[0];
  scoreChart.datasets[0].borderColor = brutalistColors[0];
  scoreChart.datasets[0].borderWidth = 1;
  scoreChart.datasets[0].borderRadius = 6;
  scoreChart.datasets[1].backgroundColor = brutalistColors[2];
  scoreChart.datasets[1].borderColor = brutalistColors[3];
  scoreChart.datasets[1].borderWidth = 1;
  scoreChart.datasets[1].borderRadius = 6;

  qualityEfficiencyChart.datasets[0].backgroundColor = brutalistColors[1];
  qualityEfficiencyChart.datasets[0].borderColor = brutalistColors[0];
  qualityEfficiencyChart.datasets[0].borderWidth = 1;
  qualityEfficiencyChart.datasets[0].borderRadius = 6;
  qualityEfficiencyChart.datasets[1].backgroundColor = brutalistColors[2];
  qualityEfficiencyChart.datasets[1].borderColor = brutalistColors[3];
  qualityEfficiencyChart.datasets[1].borderWidth = 1;
  qualityEfficiencyChart.datasets[1].borderRadius = 6;

  finalScoreChart.datasets[0].backgroundColor = pipelineData.map(
    (_, i) => brutalistColors[i % brutalistColors.length],
  );
  finalScoreChart.datasets[0].borderColor = pipelineData.map(
    (_, i) => brutalistColors[i % brutalistColors.length],
  );
  finalScoreChart.datasets[0].borderWidth = 1;
  finalScoreChart.datasets[0].borderRadius = 6;

  // --------------------------------
  // Pipeline Config Functions
  // --------------------------------
  // Custom Pipeline Config (API)
  // --------------------------------
  const fetchCustomPipeline = async () => {
    if (!collectionId) return;
    setCustomLoading(true);
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
    } finally {
      setCustomLoading(false);
    }
  };

  const saveCustomPipeline = async () => {
    if (!collectionId) return toast.error("Select a collection first.");
    setCustomSaving(true);
    try {
      const api = await axiosAuth();
      await api.post(`/collections/${collectionId}/custom-pipeline`, {
        enabled: customEnabled,
        ...customConfig,
      });
      setCustomDirty(false);
      toast.success("Custom pipeline saved");
    } catch {
      toast.error("Failed to save custom pipeline.");
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

      const {
        data: { subscription },
      } = supabase.auth.onAuthStateChange((_event, session) => {
        setUser(session?.user ?? null);
      });

      setAuthLoading(false);

      // Cleanup auth subscription on unmount
      return () => subscription.unsubscribe();
    };

    let cleanup;
    init().then((fn) => {
      cleanup = fn;
    });
    return () => {
      if (cleanup) cleanup();
    };
  }, []);

  useEffect(() => {
    if (user?.id) fetchCollections();
  }, [user?.id]);

  // Fetch global leaderboard on app load
  useEffect(() => {
    if (user?.id) fetchLeaderboard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  // Fetch available models when user logs in
  useEffect(() => {
    if (user?.id) fetchAvailableModels();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  useEffect(() => {
    if (!collectionId) return;
    setChatDisplayLimit(40);

    if (chatCache[collectionId]) {
      // Instantly show cached messages — no flash of old content
      setChatMessages(chatCache[collectionId]);
      setChatHistoryLoading(false);
    } else {
      // Clear stale messages from the previous collection IMMEDIATELY
      // so chatMessages.length === 0 → skeleton renders
      setChatMessages([]);
      setChatHistoryLoading(true);
    }

    // Share ONE auth token fetch across all parallel calls
    (async () => {
      try {
        const api = await axiosAuth();
        await Promise.all([
          // Chat history
          api
            .get(`/collections/${collectionId}/chat`)
            .then((r) => {
              const msgs = r.data.messages || [];
              setChatMessages(msgs);
              setChatCache((prev) => ({ ...prev, [collectionId]: msgs }));
            })
            .catch(() => {
              setChatMessages([]);
            }),
          // Fast history
          api
            .get(`/collections/${collectionId}/ask-history`)
            .then((r) => {
              setFastHistory(r.data.history || []);
            })
            .catch(() => setFastHistory([])),
          // Collection files
          api
            .get(`/collections/${collectionId}/files`)
            .then((r) => {
              setCollectionFiles(r.data.files || []);
            })
            .catch(() => setCollectionFiles([])),
        ]);
        // Custom pipeline has multi-state logic — called separately
        fetchCustomPipeline();
      } catch {
        // axiosAuth() itself failed — individual error toasts already handled
      } finally {
        setChatHistoryLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collectionId]);

  // Dark mode sync
  useEffect(() => {
    document.documentElement.setAttribute(
      "data-theme",
      darkMode ? "dark" : "light",
    );
    try {
      localStorage.setItem("rag-theme", darkMode ? "dark" : "light");
    } catch {}
  }, [darkMode]);

  // Auto-scroll thread to bottom on new messages
  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTo({
        top: threadRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [chatMessages, askRes]);

  // Close mode menu on click-outside
  useEffect(() => {
    const handler = (e) => {
      if (modeMenuRef.current && !modeMenuRef.current.contains(e.target)) {
        setModeMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Auto-open right panel for fast/compare, close for chat
  useEffect(() => {
    if (mode === "fast" || mode === "compare") {
      setRightPanelOpen(true);
    } else if (mode === "chat") {
      setRightPanelOpen(false);
    }
  }, [mode]);

  // --------------------------------
  // Copy to clipboard helper
  // --------------------------------
  const copyToClipboard = useCallback((text) => {
    navigator.clipboard.writeText(text).then(
      () => toast.success("Copied to clipboard"),
      () => toast.error("Failed to copy"),
    );
  }, []);

  // --------------------------------
  // UI Pieces — Claude Style
  // --------------------------------

  /* ── Sidebar Collection List ── */
  const filteredCollections = useMemo(() => {
    if (!collectionSearch.trim()) return collections;
    const q = collectionSearch.toLowerCase();
    return collections.filter((c) => c.name?.toLowerCase().includes(q));
  }, [collections, collectionSearch]);

  const SidebarCollections = () => (
    <div className="sidebarList">
      {collections.length > 3 && (
        <div className="collSearchWrap">
          <input
            className="collSearchInput"
            placeholder="Search collections..."
            value={collectionSearch}
            onChange={(e) => setCollectionSearch(e.target.value)}
          />
        </div>
      )}
      {collections.length === 0 ? (
        <div className="emptyCTA">
          <Upload size={32} />
          <div className="mini">No collections yet</div>
          <button
            className="btn primary"
            style={{ fontSize: 13 }}
            onClick={() => {
              setShowUploadModal(true);
              setUploadRes(null);
              setFiles([]);
            }}
          >
            <Upload size={14} style={{ marginRight: 6 }} /> Upload PDFs
          </button>
        </div>
      ) : (
        filteredCollections.map((c) => (
          <div
            key={c.id}
            className={`collItem ${collectionId === c.id ? "active" : ""}`}
            onClick={() => {
              setCollectionId(c.id);
              setAskRes(null);
              setUploadRes(null);
              setShowDashboard(false);
              setShowPdfViewer(false);
              setActivePdfUrl("");
              setActivePdfName("");
              setShowDocBar(false);
              setError("");
              setActiveTool("chat");
            }}
          >
            <span className="collName">{c.name}</span>
            <div className="collActions">
              <button
                className="collActionBtn"
                title="Rename"
                aria-label="Rename"
                onClick={(e) => {
                  e.stopPropagation();
                  setRenameTarget(c.id);
                  setRenameValue(c.name || "");
                  setRenameModalOpen(true);
                }}
              >
                <Pencil size={14} />
              </button>
              <button
                className="collActionBtn danger"
                title="Delete"
                aria-label="Delete"
                onClick={(e) => {
                  e.stopPropagation();
                  setDeleteTarget(c.id);
                  setDeleteModalOpen(true);
                }}
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  );

  /* ── Upload Modal ── */
  const UploadModal = () => {
    if (!showUploadModal) return null;
    return (
      <div
        className="uploadModal"
        onClick={() => {
          if (!uploading) {
            setShowUploadModal(false);
            setForceNewCollection(false);
          }
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape" && !uploading) setShowUploadModal(false);
        }}
      >
        <div
          className="uploadModalContent"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            className="uploadModalClose"
            onClick={() => {
              if (!uploading) {
                setShowUploadModal(false);
                setForceNewCollection(false);
              }
            }}
            aria-label="Close"
          >
            <X size={18} />
          </button>
          <div className="uploadModalTitle">
            <Upload size={20} style={{ marginRight: 8 }} />
            {forceNewCollection ? "New Chat" : "Add to Collection"}
          </div>
          {forceNewCollection && (
            <div className="mini">
              A new collection will be created for this chat.
            </div>
          )}
          {!forceNewCollection && collectionId && (
            <div className="mini">
              Adding to: <b>{activeCollectionName}</b>
            </div>
          )}
          {!forceNewCollection && !collectionId && (
            <div className="mini">
              No collection selected — a new one will be created automatically.
            </div>
          )}
          <div
            className={`dropZone ${dragOver ? "dragOver" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              const dropped = Array.from(e.dataTransfer.files).filter(
                (f) =>
                  f.type === "application/pdf" || f.type.startsWith("image/"),
              );
              if (dropped.length) setFiles(dropped);
              else toast.error("Only PDFs and images are supported.");
            }}
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload size={24} style={{ marginBottom: 6, opacity: 0.5 }} />
            <div>
              {dragOver
                ? "Drop files here"
                : "Drag & drop PDFs / images or click to browse"}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf,image/jpeg,image/jpg,image/png,image/webp,image/gif,image/bmp"
              multiple
              onChange={(e) => setFiles(Array.from(e.target.files || []))}
              disabled={uploading}
            />
          </div>
          {files.length > 0 && (
            <div className="fileList">
              {files.map((f, i) => (
                <div key={i}>
                  {f.type.startsWith("image/") ? (
                    <Image size={13} />
                  ) : (
                    <FileText size={13} />
                  )}{" "}
                  {f.name}{" "}
                  <span style={{ opacity: 0.6 }}>
                    ({(f.size / 1024).toFixed(0)} KB)
                  </span>
                </div>
              ))}
            </div>
          )}
          {/* ── Index Type Selector ── */}
          <div
            style={{
              margin: "12px 0 4px",
              display: "flex",
              alignItems: "center",
              gap: 16,
            }}
          >
            <span style={{ fontSize: 13, fontWeight: 600, opacity: 0.7 }}>
              Index Type
            </span>
            <label
              style={{
                fontSize: 13,
                display: "flex",
                alignItems: "center",
                gap: 4,
                cursor: "pointer",
              }}
            >
              <input
                type="radio"
                name="indexType"
                value="vector"
                checked={indexType === "vector"}
                onChange={(e) => setIndexType(e.target.value)}
                disabled={uploading}
              />
              Vector DB
            </label>
            <label
              style={{
                fontSize: 13,
                display: "flex",
                alignItems: "center",
                gap: 4,
                cursor: "pointer",
              }}
            >
              <input
                type="radio"
                name="indexType"
                value="tree"
                checked={indexType === "tree"}
                onChange={(e) => setIndexType(e.target.value)}
                disabled={uploading}
              />
              Tree Index
            </label>
          </div>
          {uploading && uploadProgress > 0 && (
            <div className="uploadProgressBar">
              <div
                className="uploadProgressFill"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          )}
          <button
            className="btn primary"
            style={{ marginTop: 12 }}
            onClick={() => uploadMultiPDF()}
            disabled={!user || uploading || files.length === 0}
          >
            {uploading ? (
              <>
                <span className="btnSpinner light" /> Uploading...{" "}
                <span className="timerBadge">{uploadElapsed}s</span>
              </>
            ) : (
              `Upload ${files.length} file(s)`
            )}
          </button>
          {uploadRes && (
            <div className="mini" style={{ marginTop: 8 }}>
              Uploaded: <b>{uploadRes.files_uploaded?.length}</b> file(s)
              {uploadRes.images_described > 0 && (
                <>
                  {" "}
                  · Images analyzed: <b>{uploadRes.images_described}</b>
                </>
              )}{" "}
              · Time: <b>{uploadRes.total_time_taken_sec}s</b>
            </div>
          )}
        </div>
      </div>
    );
  };

  /* ── Chat + Ask Thread View ── */
  const ChatThreadView = () => (
    <div
      style={{ display: "flex", flex: 1, overflow: "hidden", width: "100%" }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          flex: 1,
          minWidth: 300,
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div className="threadViewport" id="threadViewport" ref={threadRef}>
          <div className="threadInner">
            {mode === "chat" &&
              chatMessages.length === 0 &&
              chatHistoryLoading && (
                <div
                  style={{
                    padding: "24px 16px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 12,
                  }}
                >
                  {[0, 1, 2].map((i) => (
                    <div
                      key={i}
                      style={{
                        display: "flex",
                        flexDirection: i % 2 === 0 ? "row" : "row-reverse",
                        gap: 10,
                        alignItems: "flex-start",
                      }}
                    >
                      <div
                        style={{
                          width: 32,
                          height: 32,
                          borderRadius: "50%",
                          background: "var(--c-border)",
                          flexShrink: 0,
                        }}
                      />
                      <div
                        style={{
                          height: 14,
                          background: "var(--c-border)",
                          borderRadius: 6,
                          width: i === 1 ? "55%" : "72%",
                          opacity: 0.5,
                        }}
                      />
                    </div>
                  ))}
                </div>
              )}
            {mode === "chat" &&
              chatMessages.length === 0 &&
              !askRes &&
              !chatHistoryLoading && (
                <div className="emptyThread">
                  <div className="emptyIcon">
                    <MessageSquare size={40} />
                  </div>
                  <div>Start a conversation with your documents</div>
                  <div className="mini">
                    Select a collection and type a message below
                  </div>
                </div>
              )}
            {mode !== "chat" && !askRes && (
              <div className="emptyThread">
                <div className="emptyIcon">
                  {mode === "fast" ? (
                    <Zap size={40} />
                  ) : (
                    <FlaskConical size={40} />
                  )}
                </div>
                <div>
                  {mode === "fast"
                    ? "Fast Analysis Mode"
                    : "Pipeline Compare Mode"}
                </div>
                <div className="mini">
                  Ask a question to analyze your documents
                </div>
              </div>
            )}
            {mode === "chat" && chatMessages.length > chatDisplayLimit && (
              <div style={{ textAlign: "center", padding: "8px 0" }}>
                <button
                  className="btn"
                  style={{ fontSize: 12 }}
                  onClick={() => setChatDisplayLimit((l) => l + 40)}
                >
                  Load {Math.min(40, chatMessages.length - chatDisplayLimit)}{" "}
                  earlier messages
                </button>
              </div>
            )}
            {mode === "chat" &&
              chatMessages.slice(-chatDisplayLimit).map((m, i) => (
                <div key={i}>
                  <div
                    className={`msgRow ${m.role === "user" ? "user" : "assistant"}`}
                  >
                    {m.role === "assistant" && (
                      <div className="msgAvatar ai">AI</div>
                    )}
                    <div
                      className={`msgBubble ${m.role === "user" ? "user" : "assistant"}`}
                    >
                      {m.role === "assistant" && m.message ? (
                        <>
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {m.message}
                          </ReactMarkdown>
                          <button
                            className="copyBtn"
                            onClick={() => copyToClipboard(m.message)}
                            title="Copy"
                          >
                            <Copy size={12} /> Copy
                          </button>
                        </>
                      ) : (
                        m.message ||
                        (chatLoading && i === chatMessages.length - 1 ? (
                          <span style={{ opacity: 0.5 }}>Thinking...</span>
                        ) : (
                          ""
                        ))
                      )}
                    </div>
                    {m.role === "user" && (
                      <div className="msgAvatar human">
                        {user?.email?.[0]?.toUpperCase() || "U"}
                      </div>
                    )}
                  </div>
                  {m.role === "assistant" && chatAnalytics[i] && (
                    <div className="msgMeta">
                      <Zap size={11} />
                      <span>{chatAnalytics[i].pipeline}</span>
                      <span>·</span>
                      <span>{chatAnalytics[i].latency_ms} ms</span>
                      <span>·</span>
                      <span>{chatAnalytics[i].docs_retrieved} docs</span>
                      {chatAnalytics[i].smart_extract && (
                        <>
                          <span>·</span>
                          <span>smart extract</span>
                        </>
                      )}
                    </div>
                  )}
                </div>
              ))}
            {mode !== "chat" &&
              fastHistory
                .filter((entry) => entry.mode === mode)
                .map((entry, idx) => (
                  <Fragment key={entry.id || idx}>
                    <div className="msgRow user">
                      <div className="msgBubble user">{entry.question}</div>
                      <div className="msgAvatar human">
                        {user?.email?.[0]?.toUpperCase() || "U"}
                      </div>
                    </div>
                    <div className="msgRow assistant">
                      <div className="msgAvatar ai">AI</div>
                      <div className="msgBubble assistant">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {entry.answer}
                        </ReactMarkdown>
                        <div
                          style={{
                            display: "flex",
                            gap: "8px",
                            marginTop: "6px",
                          }}
                        >
                          <button
                            className="copyBtn"
                            onClick={() => copyToClipboard(entry.answer)}
                            title="Copy"
                          >
                            <Copy size={12} /> Copy
                          </button>
                          {(entry.metrics || entry.retrieval_comparison) && (
                            <button
                              className="copyBtn"
                              onClick={() => {
                                setAskRes({
                                  final_answer: entry.answer,
                                  best_pipeline: entry.best_pipeline,
                                  metrics: entry.metrics || {},
                                  retrieval_comparison:
                                    entry.retrieval_comparison || [],
                                });
                                setShowDashboard(true);
                              }}
                              title="View Results"
                            >
                              <BarChart3 size={12} /> View Results
                            </button>
                          )}
                        </div>
                        {entry.best_pipeline && (
                          <div style={{ marginTop: 8 }}>
                            <span className="bestPill">
                              <Trophy size={14} style={{ marginRight: 4 }} />{" "}
                              {entry.best_pipeline}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  </Fragment>
                ))}
            {mode !== "chat" && asking && (
              <>
                <div className="msgRow user">
                  <div className="msgBubble user">{pendingQuestion}</div>
                  <div className="msgAvatar human">
                    {user?.email?.[0]?.toUpperCase() || "U"}
                  </div>
                </div>
                <div className="msgRow assistant">
                  <div className="msgAvatar ai">AI</div>
                  <div className="msgBubble assistant">
                    <div className="skeletonWrap">
                      <div className="skeletonLine" style={{ width: "88%" }} />
                      <div className="skeletonLine" style={{ width: "72%" }} />
                      <div className="skeletonLine" style={{ width: "55%" }} />
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* Phase 2.2: Error state if no retrieval results (but not for Page Index which doesn't have retrieval_comparison) */}
            {mode !== "chat" &&
              askRes &&
              (!askRes.retrieval_comparison ||
                askRes.retrieval_comparison.length === 0) &&
              (!askRes.final_answer || askRes.final_answer.trim() === "") && (
                <div className="noResultsCard">
                  <div style={{ textAlign: "center", padding: "40px 20px" }}>
                    <AlertTriangle
                      size={32}
                      style={{ color: "var(--c-warning)", marginBottom: 12 }}
                    />
                    <div
                      style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}
                    >
                      No retrieval results available
                    </div>
                    <div
                      style={{
                        fontSize: 12,
                        color: "var(--c-text-secondary)",
                        marginBottom: 16,
                      }}
                    >
                      The pipelines returned no documents for this query.
                    </div>
                    <button
                      className="btn"
                      onClick={() => {
                        setQuestion("");
                        setAskRes(null);
                      }}
                      style={{ fontSize: 12 }}
                    >
                      Try Another Query
                    </button>
                  </div>
                </div>
              )}

            {/* Phase 2.3: Loading state during Fast query */}
            {mode === "fast" && asking && (
              <div className="loadingCard">
                <div style={{ padding: "40px 20px", textAlign: "center" }}>
                  <div
                    className="btnSpinner"
                    style={{ width: 40, height: 40, margin: "0 auto 16px" }}
                  />
                  <div
                    style={{
                      fontSize: 14,
                      fontWeight: 600,
                      color: "var(--c-text-secondary)",
                    }}
                  >
                    Querying pipelines...
                  </div>
                  <div
                    style={{
                      fontSize: 12,
                      color: "var(--c-text-muted)",
                      marginTop: 8,
                    }}
                  >
                    Retrieving and analyzing documents
                  </div>
                </div>
              </div>
            )}

            {/* Fast Mode Results */}
            {mode === "fast" && (
              <FastModeResults result={askRes} askLoading={asking} />
            )}

            {/* Compare Mode Results */}
            {mode === "compare" && (
              <CompareModeResults result={askRes} askLoading={asking} />
            )}
          </div>
        </div>
        <div className="composerWrap">
          <div className="claudeComposer">
            {showDocBar && collectionFiles.length > 0 && (
              <div
                style={{
                  display: "flex",
                  gap: 6,
                  flexWrap: "wrap",
                  padding: "8px 12px 6px",
                  borderBottom: "1px solid var(--c-border)",
                }}
              >
                {collectionFiles.map((f) => (
                  <button
                    key={f.id}
                    className="btn"
                    style={{
                      fontSize: 11,
                      padding: "3px 10px",
                      borderRadius: 20,
                      fontWeight: 500,
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                      maxWidth: 200,
                    }}
                    title={`${f.filename} | Using: ${activeCollectionIndexType === "vector" ? "Vector DB" : "Page Index"}`}
                    onClick={() => openPdfInViewer({ fileId: f.id, page: 0 })}
                  >
                    <FileText size={11} style={{ flexShrink: 0 }} />
                    <span
                      style={{
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {f.filename?.length > 16
                        ? f.filename.slice(0, 16) + "\u2026"
                        : f.filename}
                      {" | "}
                      <span style={{ color: "var(--c-text-secondary)" }}>
                        {activeCollectionIndexType === "vector"
                          ? "Vector"
                          : "Tree"}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            )}
            <div className="composerInner">
              <div className="composerTextWrap">
                <textarea
                  className="composerInput"
                  rows={1}
                  placeholder={
                    mode === "chat"
                      ? "Message your documents..."
                      : mode === "fast"
                        ? "Ask for quick analysis..."
                        : "Ask to compare all pipelines..."
                  }
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleUnifiedQuery();
                    }
                  }}
                  onInput={(e) => {
                    e.target.style.height = "auto";
                    e.target.style.height =
                      Math.min(e.target.scrollHeight, 200) + "px";
                  }}
                />
              </div>
              <div className="composerActions">
                <button
                  className="composerBtn"
                  onClick={() => {
                    setForceNewCollection(false);
                    setShowUploadModal(true);
                    setUploadRes(null);
                    setFiles([]);
                  }}
                  title="Add PDFs to this collection"
                  aria-label="Upload"
                >
                  <Paperclip size={16} />
                </button>
                {mode === "chat" && (
                  <>
                    <button
                      className="composerBtn"
                      onClick={fetchChat}
                      disabled={!collectionId}
                      title="Refresh"
                      aria-label="Refresh"
                    >
                      <RefreshCw size={16} />
                    </button>
                    <button
                      className="composerBtn"
                      onClick={() => setClearChatModalOpen(true)}
                      disabled={!collectionId}
                      title="Clear"
                      aria-label="Clear"
                    >
                      <Trash2 size={16} />
                    </button>
                  </>
                )}
                {askRes && mode !== "chat" && (
                  <button
                    className={`composerBtn ${showDashboard ? "active" : ""}`}
                    onClick={() => setShowDashboard((s) => !s)}
                    title="Results"
                    aria-label="Results"
                  >
                    <BarChart3 size={16} />
                  </button>
                )}
                {indexMissing && (
                  <button
                    className="composerBtn"
                    onClick={rebuildIndex}
                    disabled={rebuildingIndex}
                    title="Rebuild"
                    aria-label="Rebuild"
                  >
                    {rebuildingIndex ? (
                      <span className="btnSpinner" />
                    ) : (
                      <Wrench size={16} />
                    )}
                  </button>
                )}
                {collectionId && collectionFiles.length > 0 && (
                  <button
                    className={`composerBtn ${showDocBar ? "active" : ""}`}
                    onClick={() => setShowDocBar((s) => !s)}
                    title={`${collectionFiles.length} document${collectionFiles.length !== 1 ? "s" : ""} in this collection`}
                    aria-label="Toggle document list"
                  >
                    <FileText size={16} />
                    <span
                      style={{
                        fontSize: 10,
                        marginLeft: 3,
                        fontWeight: 600,
                        lineHeight: 1,
                      }}
                    >
                      {collectionFiles.length}
                    </span>
                  </button>
                )}
                <div className="composerSpacer" />
                <div className="modeMenuWrap" ref={modeMenuRef}>
                  <button
                    className="modeSelector"
                    onClick={() => setModeMenuOpen((o) => !o)}
                    title="Switch mode"
                  >
                    <span className="modeIcon">
                      {mode === "chat" ? (
                        <MessageSquare size={14} />
                      ) : mode === "fast" ? (
                        <Zap size={14} />
                      ) : (
                        <FlaskConical size={14} />
                      )}
                    </span>
                    <span className="modeName">
                      {mode === "chat"
                        ? "Chat"
                        : mode === "fast"
                          ? "Fast"
                          : "Compare"}
                    </span>
                    <span className="modeChevron">▾</span>
                  </button>
                  {modeMenuOpen && (
                    <div className="modeMenu">
                      {[
                        {
                          key: "chat",
                          icon: <MessageSquare size={14} />,
                          label: "Chat",
                          desc: "Streaming conversation",
                        },
                        {
                          key: "fast",
                          icon: <Zap size={14} />,
                          label: "Fast",
                          desc: "Quick single-pipeline answer",
                        },
                        {
                          key: "compare",
                          icon: <FlaskConical size={14} />,
                          label: "Compare",
                          desc: "Compare all 4 pipelines",
                        },
                      ].map(({ key, icon, label, desc }) => (
                        <button
                          key={key}
                          className={`modeMenuItem ${mode === key ? "active" : ""}`}
                          onClick={() => {
                            setMode(key);
                            setModeMenuOpen(false);
                          }}
                        >
                          <span className="modeMenuIcon">{icon}</span>
                          <span className="modeMenuText">
                            <span className="modeMenuLabel">{label}</span>
                            <span className="modeMenuDesc">{desc}</span>
                          </span>
                          {mode === key && (
                            <span className="modeMenuCheck">✓</span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  className="sendBtn"
                  onClick={handleUnifiedQuery}
                  disabled={
                    !user ||
                    (mode !== "image" && !collectionId) ||
                    asking ||
                    chatLoading ||
                    (mode !== "image" && !question.trim())
                  }
                  title="Send"
                  aria-label="Send"
                >
                  {asking || chatLoading ? (
                    <span className="btnSpinner light" />
                  ) : (
                    <ArrowUp size={18} />
                  )}
                </button>
              </div>
            </div>
          </div>
          {(asking || chatLoading) && (
            <div
              className="timerBadge"
              style={{ textAlign: "center", padding: "4px 0" }}
            >
              Thinking... {queryElapsed}s
            </div>
          )}
        </div>
      </div>
    </div>
  );

  /* ── Pipeline Config Panel ── */
  const PipelineConfigPanel = () => (
    <div className="configPanel">
      <div className="claudeCard">
        <div className="claudeCardHead">Custom Pipeline Configuration</div>
        <div className="claudeCardBody">
          {/* ── Loading state ── */}
          {customLoading && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                padding: "60px 0",
                gap: 14,
              }}
            >
              <div
                className="btnSpinner"
                style={{ width: 32, height: 32, borderWidth: 3 }}
              />
              <div
                style={{
                  color: "var(--c-text-muted)",
                  fontSize: 13,
                  fontWeight: 500,
                }}
              >
                Loading configuration…
              </div>
            </div>
          )}

          {/* ── Empty state ── */}
          {!customLoading && !collectionId && (
            <div style={{ textAlign: "center", padding: "40px 0" }}>
              <div className="mini" style={{ marginBottom: 14 }}>
                Select a collection to configure its pipeline.
              </div>
            </div>
          )}

          {/* ── Results state ── */}
          {!customLoading && collectionId && (
            <>
              <div
                style={{
                  display: "flex",
                  gap: 10,
                  alignItems: "center",
                  marginBottom: 16,
                }}
              >
                <span className={`statusDot ${customEnabled ? "on" : "off"}`} />
                <span style={{ fontWeight: 600 }}>
                  {customEnabled ? "Enabled" : "Disabled"}
                </span>
                {customDirty && (
                  <span className="bestPill" style={{ fontSize: 11 }}>
                    Unsaved
                  </span>
                )}
              </div>

              <div className="btnRow" style={{ marginBottom: 16 }}>
                <button
                  className={`btn ${customEnabled ? "primary" : ""}`}
                  onClick={() => {
                    setCustomEnabled((v) => !v);
                    setCustomDirty(true);
                  }}
                >
                  {customEnabled ? "Custom: ON" : "Custom: OFF"}
                </button>
                <button className="btn" onClick={applyRecommended}>
                  Use Recommended
                </button>
              </div>

              <div
                className="btnRow"
                style={{ marginBottom: 16, flexWrap: "wrap" }}
              >
                <button
                  className="btn"
                  disabled={presetApplying}
                  onClick={() => applyPipelinePreset("fast")}
                >
                  Preset: Fast
                </button>
                <button
                  className="btn"
                  disabled={presetApplying}
                  onClick={() => applyPipelinePreset("balanced")}
                >
                  Preset: Balanced
                </button>
                <button
                  className="btn"
                  disabled={presetApplying}
                  onClick={() => applyPipelinePreset("accurate")}
                >
                  Preset: Accurate
                </button>
                <button
                  className="btn"
                  disabled={presetApplying}
                  onClick={() => applyPipelinePreset("deepsearch")}
                >
                  Preset: DeepSearch
                </button>
              </div>

              <div className="configGrid">
                <div>
                  <label className="mini">Chunk Size</label>
                  <input
                    type="number"
                    className="claudeInput"
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
                    className="claudeInput"
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
                    className="claudeInput"
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
                    className="claudeInput"
                    value={customConfig.search_type}
                    onChange={(e) =>
                      updateCustomField("search_type", e.target.value)
                    }
                  >
                    <option value="similarity">Similarity</option>
                    <option value="mmr">MMR</option>
                    <option value="similarity_score_threshold">
                      Score Threshold
                    </option>
                  </select>
                </div>
              </div>

              <button
                className="btn primary"
                onClick={saveCustomPipeline}
                disabled={customSaving}
                style={{ marginTop: 16 }}
              >
                {customSaving ? (
                  <>
                    <span className="btnSpinner" /> Saving...
                  </>
                ) : customDirty ? (
                  "Save Custom Pipeline *"
                ) : (
                  "Save Custom Pipeline"
                )}
              </button>

              <div className="mini" style={{ marginTop: 10 }}>
                In Compare mode the system runs 4 defaults + this optional
                custom pipeline with your custom chunk settings.
              </div>
              <div className="mini" style={{ fontStyle: "italic" }}>
                All settings below are fully customizable: Adjust chunk size,
                overlap, top-K, and search type as needed.
              </div>
              <div className="mini">
                Current: {customConfig.chunk_size}ch | {customConfig.overlap}ov
                | k{customConfig.top_k} | {customConfig.search_type}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );

  /* ── Image Test Panel ── */
  const ImageTestPanel = () => (
    <div
      className="configPanel"
      style={{ overflowY: "auto", overflowX: "hidden" }}
    >
      <div className="claudeCard">
        <div className="claudeCardHead">Image Analysis</div>
        <div className="claudeCardBody">
          {/* ── Loading state ── */}
          {imgLoading && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                padding: "60px 0",
                gap: 14,
              }}
            >
              <div
                className="btnSpinner"
                style={{ width: 32, height: 32, borderWidth: 3 }}
              />
              <div
                style={{
                  color: "var(--c-text-muted)",
                  fontSize: 13,
                  fontWeight: 500,
                }}
              >
                Analyzing image…
              </div>
            </div>
          )}

          {/* ── Input state ── */}
          {!imgLoading && !imgRes && (
            <>
              <div className="mini" style={{ marginBottom: 12 }}>
                Upload an image and ask a question to test RAG vision accuracy.
              </div>
              <input
                className="claudeInput"
                type="file"
                accept="image/*"
                style={{ padding: 8 }}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  setImgFile(f);
                  setImgPreview(URL.createObjectURL(f));
                  setImgRes(null);
                }}
              />
              {imgPreview && (
                <div
                  style={{
                    marginTop: 12,
                    display: "flex",
                    justifyContent: "center",
                    background: "var(--c-surface)",
                    border: "1px solid var(--c-border)",
                    borderRadius: 10,
                    padding: 6,
                  }}
                >
                  <img
                    src={imgPreview}
                    alt="preview"
                    style={{
                      maxHeight: 180,
                      maxWidth: "100%",
                      width: "auto",
                      borderRadius: 7,
                      objectFit: "contain",
                    }}
                  />
                </div>
              )}
              <input
                className="claudeInput"
                placeholder="Ask something about the image..."
                value={imgQuestion}
                onChange={(e) => setImgQuestion(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleImageTest()}
                style={{ marginTop: 12 }}
              />
              <div className="btnRow" style={{ marginTop: 12 }}>
                <button
                  className="btn primary"
                  onClick={() => handleImageTest()}
                  disabled={!user || !imgFile || !imgQuestion.trim()}
                >
                  Analyze Image
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
                  Clear
                </button>
              </div>
            </>
          )}

          {/* ── Results state ── */}
          {!imgLoading && imgRes && (
            <>
              {/* Hero row: thumbnail + confidence */}
              <div className="imgResultHero">
                {imgPreview && (
                  <img
                    src={imgPreview}
                    alt="analyzed"
                    className="imgResultThumb"
                  />
                )}
                <div className="imgResultMeta">
                  <div className="imgConfLabel">CONFIDENCE</div>
                  <div
                    className="imgConfScore"
                    style={{
                      color:
                        imgRes.confidence_score >= 7
                          ? "var(--c-accent)"
                          : imgRes.confidence_score >= 4
                            ? "#c49a3a"
                            : "var(--c-danger)",
                    }}
                  >
                    {Number(imgRes.confidence_score ?? 0).toFixed(1)}
                    <span className="imgConfDenom">&nbsp;/ 10</span>
                  </div>
                  <div className="imgConfBarTrack">
                    <div
                      className="imgConfBarFill"
                      style={{
                        width: `${(imgRes.confidence_score / 10) * 100}%`,
                        background:
                          imgRes.confidence_score >= 7
                            ? "var(--c-accent)"
                            : imgRes.confidence_score >= 4
                              ? "#c49a3a"
                              : "var(--c-danger)",
                      }}
                    />
                  </div>
                  {imgRes.failure_type && (
                    <div className="imgFailureBadge">{imgRes.failure_type}</div>
                  )}
                </div>
              </div>

              {/* Answer */}
              <div className="imgAnswerWrap">
                <div className="imgAnswerText">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {imgRes.final_answer}
                  </ReactMarkdown>
                </div>
                <button
                  className="copyBtn"
                  onClick={() => {
                    navigator.clipboard.writeText(imgRes.final_answer);
                    toast.success("Copied!");
                  }}
                >
                  <Copy size={12} /> Copy
                </button>
              </div>

              {/* Collapsible description */}
              <div className="imgDetailsSection">
                <button
                  className="imgDetailsToggle"
                  onClick={() => setShowImgAdvanced((s) => !s)}
                >
                  {showImgAdvanced
                    ? "▾ Hide description"
                    : "▸ Show extracted description"}
                </button>
                {showImgAdvanced && (
                  <div className="imgDescriptionBox">
                    {imgRes.extracted_description}
                  </div>
                )}
              </div>

              {/* Metrics strip — always visible */}
              <div className="imgMetricsStrip">
                {[
                  {
                    label: "Vision",
                    value: `${imgRes.metrics?.latency?.vision_ms ?? 0} ms`,
                  },
                  {
                    label: "LLM",
                    value: `${imgRes.metrics?.latency?.llm_ms ?? 0} ms`,
                  },
                  {
                    label: "Total",
                    value: `${imgRes.metrics?.latency?.total_ms ?? 0} ms`,
                  },
                  {
                    label: "Tokens",
                    value: imgRes.metrics?.tokens?.total_tokens ?? 0,
                  },
                  {
                    label: "Cost",
                    value: `$${imgRes.metrics?.tokens?.estimated_cost_usd ?? 0}`,
                  },
                ].map((m) => (
                  <div key={m.label} className="imgMetricItem">
                    <span className="imgMetricLabel">{m.label}</span>
                    <span className="imgMetricVal">{m.value}</span>
                  </div>
                ))}
              </div>

              {/* Follow-up + actions */}
              <div className="imgFollowUp">
                <input
                  className="claudeInput"
                  placeholder="Ask a follow-up about the same image…"
                  value={imgQuestion}
                  onChange={(e) => setImgQuestion(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleImageTest()}
                  style={{ flex: 1 }}
                />
                <button
                  className="btn primary"
                  onClick={() => handleImageTest()}
                  disabled={!imgQuestion.trim()}
                >
                  Ask Again
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
                  New
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );

  /* ── Results Dashboard (Claude style) ── */
  const ResultsDashboard = () => {
    if (!showDashboard || !askRes || mode === "chat") return null;

    // In fast mode, hide analytics when the AI couldn't find an answer
    const _noAnswerPhrases = [
      "i don't know based on the documents",
      "i do not know based on the documents",
      "i don't know based on",
      "cannot find",
      "no information",
      "not found in the documents",
      "not present in the documents",
      "not mentioned in the",
    ];
    const hasNoAnswer =
      !askRes.final_answer ||
      askRes.final_answer.trim() === "" ||
      _noAnswerPhrases.some((p) =>
        askRes.final_answer?.toLowerCase().includes(p),
      );

    if (mode === "fast" && hasNoAnswer) {
      return null;
    }

    return (
      <div className="resultsArea">
        <div className="resultsHeader">
          <div
            style={{
              fontFamily: "var(--font-serif)",
              fontSize: 18,
              fontWeight: 600,
            }}
          >
            Results &amp; Analysis
          </div>
          <button
            className="btn danger"
            onClick={() => setShowDashboard(false)}
          >
            Close
          </button>
        </div>

        <div className="metricsRow">
          <div className="metricPill best">
            <div className="metricLabel">Best Pipeline</div>
            <div className="metricValue">{askRes.best_pipeline}</div>
          </div>
        </div>

        <div className="finalAnswer">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {askRes.final_answer}
          </ReactMarkdown>
          <button
            className="copyBtn"
            onClick={() => copyToClipboard(askRes.final_answer)}
            title="Copy"
          >
            <Copy size={12} /> Copy
          </button>
        </div>

        {/* Performance Breakdown */}
        <div className="claudeCard" style={{ marginTop: 16 }}>
          <div className="claudeCardHead">Performance Breakdown</div>
          <div className="claudeCardBody">
            <div className="perfGrid">
              <div className="perfCard">
                <div className="perfTitle">Latency</div>
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
                  <span>Smart Extract</span>
                  <b>{fmtMs(safeMetrics?.timings_ms?.smart_extract_ms)}</b>
                </div>
                <div className="perfRow">
                  <span>Total</span>
                  <b>{fmtMs(safeMetrics?.timings_ms?.total_ms)}</b>
                </div>
              </div>

              <div className="perfCard">
                <div className="perfTitle">Tokens &amp; Cost</div>
                <div className="perfRow">
                  <span>Prompt Tokens</span>
                  <b>{fmtNum(safeMetrics?.tokens?.prompt_tokens)}</b>
                </div>
                <div className="perfRow">
                  <span>Completion</span>
                  <b>{fmtNum(safeMetrics?.tokens?.completion_tokens)}</b>
                </div>
                <div className="perfRow">
                  <span>Total Tokens</span>
                  <b>{fmtNum(safeMetrics?.tokens?.total_tokens)}</b>
                </div>
                <div className="perfRow">
                  <span>Cost</span>
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
              <div style={{ marginTop: 16 }}>
                <div className="perfTitle">Latency Stages</div>
                <div className="chartCanvas">
                  <Bar data={latencyChart} options={brutalistChartOptions} />
                </div>
              </div>
            )}

            {safeMetrics?.pipeline_latencies?.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div className="perfTitle">Per-Pipeline Latency</div>
                {safeMetrics.pipeline_latencies.map((pl, idx) => (
                  <div
                    key={idx}
                    className="perfCard"
                    style={{
                      marginBottom: 8,
                      background: idx === 0 ? "var(--c-winner-bg)" : undefined,
                    }}
                  >
                    <b>{pl.pipeline}</b>
                    <div className="perfRow">
                      <span>Retrieval</span>
                      <b>{fmtMs(pl.retrieval_ms)}</b>
                    </div>
                    <div className="perfRow">
                      <span>Context Build</span>
                      <b>{fmtMs(pl.context_build_ms)}</b>
                    </div>
                    <div className="perfRow">
                      <span>Scoring</span>
                      <b>{fmtMs(pl.scoring_ms)}</b>
                    </div>
                    <div className="perfRow">
                      <span>Total</span>
                      <b>{fmtMs(pl.total_ms)}</b>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {askRes?.retrieval_comparison?.length > 0 && (
          <div>
            {/* ── Side-by-Side Compare Grid (compare mode only) ── */}
            {askRes.mode === "compare" &&
              askRes.retrieval_comparison.some((p) => p.answer) && (
                <div style={{ marginBottom: 22 }}>
                  <div className="pipeTableTitle" style={{ marginBottom: 12 }}>
                    🔀 Side-by-Side — All Pipeline Answers
                  </div>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: 14,
                    }}
                  >
                    {askRes.retrieval_comparison.slice(0, 4).map((p, idx) => (
                      <div
                        key={idx}
                        style={{
                          border:
                            idx === 0
                              ? "2px solid #ae5630"
                              : "1px solid rgba(168,166,156,0.3)",
                          borderRadius: 10,
                          padding: "14px 16px",
                          background: darkMode ? "#2a2a28" : "#faf9f6",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            marginBottom: 8,
                          }}
                        >
                          <span
                            style={{
                              fontWeight: 700,
                              fontSize: 13,
                              color: darkMode ? "#ddd" : "#333",
                            }}
                          >
                            {shortLabel(p.pipeline)}
                            {idx === 0 && (
                              <span
                                style={{
                                  marginLeft: 8,
                                  fontSize: 11,
                                  background: "#ae5630",
                                  color: "#fff",
                                  padding: "1px 7px",
                                  borderRadius: 10,
                                }}
                              >
                                Winner
                              </span>
                            )}
                          </span>
                          <span
                            style={{
                              fontSize: 12,
                              color: "#ae5630",
                              fontWeight: 600,
                            }}
                          >
                            ★ {(p.scores?.final ?? 0).toFixed(2)}
                          </span>
                        </div>
                        <div
                          style={{
                            fontSize: 13,
                            color: darkMode ? "#ccc" : "#444",
                            lineHeight: 1.65,
                            maxHeight: 220,
                            overflowY: "auto",
                          }}
                        >
                          {p.answer ? (
                            p.answer
                          ) : (
                            <em style={{ opacity: 0.5 }}>
                              No answer generated
                            </em>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

            <div className="pipeGrid">
              {(showAllPipelines
                ? askRes.retrieval_comparison
                : askRes.retrieval_comparison.slice(0, 3)
              ).map((p, idx) => {
                const pipelineLabel = shortLabel(p.pipeline);
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
                      {pipelineLabel}
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
                    {p.scores && (
                      <div className="scoreGrid">
                        {[
                          { label: "Relevance", key: "relevance" },
                          { label: "Grounded", key: "grounded" },
                          { label: "Quality", key: "quality" },
                          { label: "Efficiency", key: "efficiency" },
                        ].map(({ label, key }) => (
                          <div key={key} className="scoreBarRow">
                            <span className="scoreBarLabel">{label}</span>
                            <div className="scoreBar">
                              <div
                                className="scoreBarFill"
                                style={{
                                  width: `${(p.scores[key] ?? 0) * 100}%`,
                                }}
                              />
                            </div>
                            <span className="scoreBarVal">
                              {(p.scores[key] ?? 0).toFixed(2)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            {askRes.retrieval_comparison.length > 3 && (
              <button
                className="btn"
                style={{ marginTop: 10, width: "100%" }}
                onClick={() => setShowAllPipelines((v) => !v)}
              >
                {showAllPipelines
                  ? "Show top 3"
                  : `Show all ${askRes.retrieval_comparison.length} pipelines`}
              </button>
            )}

            {/* ── Winner Insight ── */}
            {askRes.retrieval_comparison.length >= 2 &&
              (() => {
                const winner = askRes.retrieval_comparison[0];
                const runnerUp = askRes.retrieval_comparison[1];
                const dims = ["relevance", "grounded", "quality", "efficiency"];
                const edges = dims
                  .map((d) => ({
                    dim: d,
                    delta:
                      (winner.scores?.[d] ?? 0) - (runnerUp.scores?.[d] ?? 0),
                  }))
                  .filter((x) => x.delta > 0)
                  .sort((a, b) => b.delta - a.delta);
                const topEdge = edges[0];
                return (
                  <div className="winnerInsight">
                    <div className="winnerInsightTitle">
                      🏆 Why {shortLabel(winner.pipeline)} Won
                    </div>
                    <div className="winnerInsightBody">
                      {topEdge ? (
                        <>
                          Leading advantage in{" "}
                          <strong style={{ textTransform: "capitalize" }}>
                            {topEdge.dim}
                          </strong>{" "}
                          (
                          <strong>
                            {(winner.scores?.[topEdge.dim] ?? 0).toFixed(2)}
                          </strong>{" "}
                          vs {(runnerUp.scores?.[topEdge.dim] ?? 0).toFixed(2)}
                          ). Final score:{" "}
                          <strong>
                            {(winner.scores?.final ?? 0).toFixed(2)}
                          </strong>{" "}
                          vs {(runnerUp.scores?.final ?? 0).toFixed(2)}.
                        </>
                      ) : (
                        <>
                          Outperformed all other pipelines on overall final
                          score ({(winner.scores?.final ?? 0).toFixed(2)}).{" "}
                        </>
                      )}
                    </div>
                  </div>
                );
              })()}

            {/* ── Full Comparison Table ── */}
            <div className="pipeTableWrap">
              <div className="pipeTableTitle">Full Pipeline Comparison</div>
              <table className="pipeTable">
                <thead>
                  <tr>
                    <th>Pipeline</th>
                    <th>Chunk</th>
                    <th>Overlap</th>
                    <th>Top-K</th>
                    <th>Search</th>
                    <th>Retrieval (s)</th>
                    <th>Relevance</th>
                    <th>Grounded</th>
                    <th>Quality</th>
                    <th>Efficiency</th>
                    <th>Final ★</th>
                  </tr>
                </thead>
                <tbody>
                  {askRes.retrieval_comparison.map((p, idx) => (
                    <tr
                      key={idx}
                      className={idx === 0 ? "pipeTableWinner" : ""}
                    >
                      <td title={p.pipeline}>{shortLabel(p.pipeline)}</td>
                      <td>{p.chunk_size}</td>
                      <td>{p.overlap}</td>
                      <td>{p.top_k}</td>
                      <td>{p.search_type}</td>
                      <td>{p.retrieval_time_sec}</td>
                      <td>{(p.scores?.relevance ?? 0).toFixed(2)}</td>
                      <td>{(p.scores?.grounded ?? 0).toFixed(2)}</td>
                      <td>{(p.scores?.quality ?? 0).toFixed(2)}</td>
                      <td>{(p.scores?.efficiency ?? 0).toFixed(2)}</td>
                      <td>
                        <strong>{(p.scores?.final ?? 0).toFixed(2)}</strong>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="btnRow" style={{ marginTop: 14 }}>
          <button
            className="btn"
            onClick={downloadReportTXT}
            disabled={downloadingReport}
          >
            {downloadingReport ? (
              <>
                <span className="btnSpinner" /> Generating...
              </>
            ) : (
              "Export TXT"
            )}
          </button>
          <button
            className="btn"
            onClick={downloadReportJSON}
            disabled={downloadingReport}
          >
            Export JSON
          </button>
          <button
            className="btn"
            onClick={downloadReportCSV}
            disabled={downloadingReport}
          >
            Export CSV
          </button>
          <button
            className="btn"
            onClick={() => downloadReportViaApi("pdf")}
            disabled={downloadingReport}
          >
            Export PDF
          </button>
          <button
            className="btn primary"
            onClick={() => {
              if (!collectionId) return;
              if (!collectionFiles.length) fetchCollectionFiles();
              setShowPdfViewer((s) => !s);
              if (!activePdfUrl) openPdfInViewer({ page: null });
            }}
          >
            {showPdfViewer ? "Hide PDF" : "Open PDF"}
          </button>
          <button
            className="btn"
            onClick={() => {
              setActiveTool("chunks");
              setChunkExplorerOpen(true);
              setChunkOffset(0);
              fetchChunks();
            }}
            disabled={!collectionId}
          >
            Chunk Explorer
          </button>
        </div>

        {showPdfViewer && activePdfUrl && (
          <div className="pdfWrap">
            <div className="mini">
              Viewing: <b>{activePdfName || "PDF"}</b>
            </div>
            <iframe
              title="PDF Preview"
              src={activePdfUrl}
              style={{
                width: "100%",
                height: 500,
                border: "1px solid var(--c-border)",
                borderRadius: 12,
              }}
            />
          </div>
        )}
      </div>
    );
  };

  /* ── Phase 3.1: Fast Mode Analytics Card Component ── */
  const FastModeAnalyticsCard = ({ metrics, onExpand }) => {
    if (!metrics) return null;

    const safeMetrics = metrics || {};

    // Calculate best pipeline
    const bestPipeline =
      safeMetrics.pipeline_latencies?.length > 0
        ? safeMetrics.pipeline_latencies.reduce((best, current) =>
            current.total_ms < best.total_ms ? current : best,
          )
        : null;

    return (
      <div className="analyticsCard">
        <div className="analyticsCardHeader">
          <div style={{ fontSize: 14, fontWeight: 600 }}>Query Metrics</div>
          <button
            className="btn"
            onClick={onExpand}
            style={{ fontSize: 11, padding: "6px 12px" }}
          >
            Expand
          </button>
        </div>

        {/* Metrics Grid: 2x2 on desktop, 1 column on mobile */}
        <div className="metricsGrid">
          <div className="metricItem">
            <div className="metricLabel">Total Latency</div>
            <div className="metricValue">
              {fmtMs(safeMetrics.total_ms || 0)}
            </div>
          </div>
          <div className="metricItem">
            <div className="metricLabel">Tokens Used</div>
            <div className="metricValue">{safeMetrics.tokens?.total || 0}</div>
          </div>
          <div className="metricItem">
            <div className="metricLabel">Cost</div>
            <div className="metricValue">
              ${(safeMetrics.cost || 0).toFixed(4)}
            </div>
          </div>
          <div className="metricItem">
            <div className="metricLabel">Best Pipeline</div>
            <div className="metricValue">
              {bestPipeline ? shortLabel(bestPipeline.pipeline) : "N/A"}
            </div>
          </div>
        </div>

        {/* Pipeline Latency Bars */}
        {safeMetrics.pipeline_latencies?.length > 0 && (
          <div className="pipelinesBars">
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                marginBottom: 12,
                color: "var(--c-text-secondary)",
              }}
            >
              Per-Pipeline Latency
            </div>
            {safeMetrics.pipeline_latencies.slice(0, 4).map((pl, idx) => (
              <div key={idx} className="pipelineBar">
                <div style={{ fontSize: 11, marginBottom: 4, fontWeight: 500 }}>
                  {shortLabel(pl.pipeline)}
                </div>
                <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                  <div
                    style={{
                      fontSize: 12,
                      fontWeight: 700,
                      minWidth: 60,
                      textAlign: "right",
                      color: "var(--c-accent)",
                    }}
                  >
                    {fmtMs(pl.total_ms)}
                  </div>
                  <div
                    style={{
                      flex: 1,
                      height: 8,
                      background: "var(--c-border)",
                      borderRadius: 3,
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        height: "100%",
                        background:
                          idx === 0 ? "var(--c-success)" : "var(--c-info)",
                        width: `${Math.min(100, (pl.total_ms / (Math.max(...safeMetrics.pipeline_latencies.map((p) => p.total_ms)) || 1)) * 100)}%`,
                        transition: "width 0.3s ease",
                      }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  /* ── Leaderboard Panel ── */
  const LeaderboardPanel = () => (
    <div className="configPanel">
      <div className="claudeCard">
        <div className="claudeCardHead">Leaderboard</div>
        <div className="claudeCardBody">
          {/* ── Loading state: full-panel spinner ── */}
          {leaderboardLoading && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                padding: "60px 0",
                gap: 14,
              }}
            >
              <div
                className="btnSpinner"
                style={{
                  width: 32,
                  height: 32,
                  borderWidth: 3,
                }}
              />
              <div
                style={{
                  color: "var(--c-text-muted)",
                  fontSize: 13,
                  fontWeight: 500,
                }}
              >
                Fetching stats…
              </div>
            </div>
          )}

          {/* ── Empty state: no data yet ── */}
          {!leaderboardLoading && !leaderboard && (
            <div style={{ textAlign: "center", padding: "40px 0" }}>
              <div className="mini" style={{ marginBottom: 14 }}>
                Ask questions to generate stats.
              </div>
              <button className="btn primary" onClick={fetchLeaderboard}>
                Refresh
              </button>
            </div>
          )}

          {/* ── Results state ── */}
          {!leaderboardLoading && leaderboard && (
            <>
              <div className="btnRow" style={{ marginBottom: 16 }}>
                <button className="btn primary" onClick={fetchLeaderboard}>
                  Refresh
                </button>
              </div>

              <div className="metricsRow" style={{ marginBottom: 16 }}>
                <div className="metricPill">
                  <div className="metricLabel">Questions</div>
                  <div className="metricValue">
                    {leaderboard.total_questions}
                  </div>
                </div>
                <div className="metricPill">
                  <div className="metricLabel">Chat</div>
                  <div className="metricValue">
                    {leaderboard.chat_interactions || 0}
                  </div>
                </div>
                <div className="metricPill">
                  <div className="metricLabel">Best Today</div>
                  <div className="metricValue">
                    {leaderboard.best_pipeline_today || "N/A"}
                  </div>
                </div>
              </div>

              {leaderboard.pipelines?.map((p, i) => {
                const label = `Pipeline ${i + 1}`;
                const scoreDisplay =
                  p.leaderboard_score != null
                    ? `${(p.leaderboard_score * 100).toFixed(1)}%`
                    : p.avg_final_score;
                return (
                  <div
                    key={i}
                    className={`pipeCard ${i === 0 ? "winner" : ""}`}
                    style={{ marginBottom: 8 }}
                  >
                    <div className="pipeTop">
                      <div
                        className="pipeRank"
                        style={{ fontSize: 14, fontWeight: 600 }}
                      >
                        {label}
                      </div>
                      <div className="pipeScore">{scoreDisplay}</div>
                    </div>
                    <div className="pipeName">
                      {p.pipeline}
                      <div
                        className="pipeSubname"
                        style={{ fontSize: 11, opacity: 0.7 }}
                      >
                        Avg Score: {p.avg_final_score}/10
                      </div>
                    </div>
                    <div className="mini">
                      Wins: <b>{p.wins}</b> ({(p.win_rate * 100).toFixed(1)}%) |
                      Retrieval:{" "}
                      <b>
                        {p.avg_retrieval_ms
                          ? `${p.avg_retrieval_ms} ms`
                          : `${p.avg_retrieval_time_sec}s`}
                      </b>
                      {(p.avg_total_ms > 0 || p.avg_total_time_sec > 0) && (
                        <span>
                          {" "}
                          | Total:{" "}
                          <b>
                            {p.avg_total_ms
                              ? `${p.avg_total_ms} ms`
                              : `${p.avg_total_time_sec}s`}
                          </b>
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>
      </div>
    </div>
  );

  /* ── Chunk Explorer Panel ── */
  const highlightChunkText = (text, query) => {
    if (!query || !query.trim()) return <span>{text}</span>;
    const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const parts = text.split(new RegExp(`(${escaped})`, "gi"));
    return (
      <span>
        {parts.map((part, i) =>
          part.toLowerCase() === query.toLowerCase() ? (
            <mark
              key={i}
              style={{
                background: "#f59e0b44",
                color: "inherit",
                borderRadius: 2,
                padding: "0 2px",
                fontWeight: 700,
              }}
            >
              {part}
            </mark>
          ) : (
            <span key={i}>{part}</span>
          ),
        )}
      </span>
    );
  };

  const ChunkExplorerPanel = () => {
    if (!chunkExplorerOpen && activeTool !== "chunks") return null;

    const isTreeCollection = activeCollectionIndexType === "tree";
    if (isTreeCollection) {
      return (
        <TreeViewer
          collectionId={collectionId}
          axiosAuth={axiosAuth}
          onBack={() => {
            setActiveTool("chat");
            setChunkExplorerOpen(false);
          }}
        />
      );
    }

    const normalizedTreeQuery = chunkQuery.trim().toLowerCase();

    const nodeMatches = (node) => {
      if (!normalizedTreeQuery) return true;
      const title = (node?.title || "").toLowerCase();
      const summary = (node?.summary || "").toLowerCase();
      const text = (node?.text || "").toLowerCase();
      return (
        title.includes(normalizedTreeQuery) ||
        summary.includes(normalizedTreeQuery) ||
        text.includes(normalizedTreeQuery)
      );
    };

    const subtreeMatches = (node) => {
      if (nodeMatches(node)) return true;
      const children = Array.isArray(node?.children) ? node.children : [];
      return children.some((child) => subtreeMatches(child));
    };

    const toggleNode = (nodeId) => {
      setTreeExpanded((prev) => ({ ...prev, [nodeId]: !prev[nodeId] }));
    };

    const countNodes = (node) => {
      if (!node) return 0;
      const children = Array.isArray(node.children) ? node.children : [];
      return 1 + children.reduce((sum, child) => sum + countNodes(child), 0);
    };

    const countLeaves = (node) => {
      if (!node) return 0;
      const children = Array.isArray(node.children) ? node.children : [];
      if (!children.length) return 1;
      return children.reduce((sum, child) => sum + countLeaves(child), 0);
    };

    const expandAllNodes = () => {
      if (!treeData) return;
      const all = {};
      const walk = (node) => {
        if (!node) return;
        if (node.id) all[node.id] = true;
        const children = Array.isArray(node.children) ? node.children : [];
        children.forEach(walk);
      };
      walk(treeData);
      setTreeExpanded(all);
    };

    const collapseAllNodes = () => {
      if (!treeData) return;
      setTreeExpanded(treeData.id ? { [treeData.id]: true } : {});
    };

    const renderTreeNode = (node, depth = 0) => {
      if (!node) return null;
      if (!subtreeMatches(node)) return null;

      const children = Array.isArray(node.children) ? node.children : [];
      const hasChildren = children.length > 0;
      const expanded = treeExpanded[node.id] ?? depth < 2;

      return (
        <div key={node.id || `${node.title}-${depth}`} className="treeNodeWrap">
          <div className="treeNode" style={{ marginLeft: depth * 12 }}>
            <button
              className="treeToggle"
              onClick={() => hasChildren && node.id && toggleNode(node.id)}
              disabled={!hasChildren}
              aria-label={
                hasChildren ? (expanded ? "Collapse" : "Expand") : "Leaf"
              }
            >
              {hasChildren ? (
                expanded ? (
                  <ChevronDown size={14} />
                ) : (
                  <ChevronRight size={14} />
                )
              ) : (
                <span className="treeDot" />
              )}
            </button>

            <div className="treeContent">
              <div className="treeTitle">{node.title || "Untitled node"}</div>
              {node.summary && (
                <div className="treeSummary">
                  {highlightChunkText(node.summary, chunkQuery)}
                </div>
              )}
              {!hasChildren && node.text && (
                <div className="treeLeafText">
                  {highlightChunkText(
                    node.text.length > 240
                      ? `${node.text.slice(0, 240)}...`
                      : node.text,
                    chunkQuery,
                  )}
                </div>
              )}
            </div>
          </div>

          {hasChildren && expanded && (
            <div className="treeChildren">
              {children.map((child) => renderTreeNode(child, depth + 1))}
            </div>
          )}
        </div>
      );
    };

    return (
      <div className="configPanel">
        <div className="claudeCard">
          <div className="claudeCardHead">
            {isTreeCollection ? "Tree Explorer" : "Chunk Explorer"}
          </div>
          <div className="claudeCardBody">
            {/* ── Filter bar — always visible ── */}
            <div
              style={{
                display: "flex",
                gap: 8,
                flexWrap: "wrap",
                marginBottom: 10,
              }}
            >
              <input
                className="claudeInput"
                placeholder={
                  isTreeCollection
                    ? "Search tree nodes..."
                    : "Search chunk text..."
                }
                value={chunkQuery}
                style={{ flex: 1, minWidth: 160 }}
                onChange={(e) => setChunkQuery(e.target.value)}
                onKeyDown={(e) =>
                  e.key === "Enter" &&
                  (isTreeCollection
                    ? fetchTreeIndex()
                    : (setChunkOffset(0), fetchChunks()))
                }
              />
              {!isTreeCollection && (
                <>
                  <input
                    className="claudeInput"
                    placeholder="Page #"
                    value={chunkFilterPage}
                    style={{ width: 72 }}
                    onChange={(e) => setChunkFilterPage(e.target.value)}
                    onKeyDown={(e) =>
                      e.key === "Enter" && (setChunkOffset(0), fetchChunks())
                    }
                  />
                  <input
                    className="claudeInput"
                    placeholder="Pipeline"
                    value={chunkFilterPipeline}
                    style={{ width: 130 }}
                    list="chunk-pipeline-list"
                    onChange={(e) => setChunkFilterPipeline(e.target.value)}
                    onKeyDown={(e) =>
                      e.key === "Enter" && (setChunkOffset(0), fetchChunks())
                    }
                  />
                  <datalist id="chunk-pipeline-list">
                    {knownPipelines.map((p) => (
                      <option key={p} value={p} />
                    ))}
                  </datalist>
                </>
              )}
              <button
                className="btn primary"
                onClick={() => {
                  if (isTreeCollection) {
                    fetchTreeIndex();
                  } else {
                    setChunkOffset(0);
                    fetchChunks();
                  }
                }}
                disabled={isTreeCollection ? treeLoading : chunksLoading}
              >
                {(isTreeCollection ? treeLoading : chunksLoading) ? (
                  <span
                    className="btnSpinner"
                    style={{ width: 14, height: 14, borderWidth: 2 }}
                  />
                ) : (
                  "Search"
                )}
              </button>
              {isTreeCollection && (
                <>
                  <button
                    className="btn"
                    onClick={expandAllNodes}
                    disabled={!treeData || treeLoading}
                  >
                    Expand all
                  </button>
                  <button
                    className="btn"
                    onClick={collapseAllNodes}
                    disabled={!treeData || treeLoading}
                  >
                    Collapse all
                  </button>
                </>
              )}
            </div>

            <div className="btnRow" style={{ marginBottom: 10 }}>
              <button
                className="btn"
                onClick={() => {
                  setActiveTool("chat");
                  setChunkExplorerOpen(false);
                }}
              >
                Back to Chat
              </button>
              {!isTreeCollection && chunks.length > 0 && (
                <div className="mini" style={{ marginLeft: "auto" }}>
                  Showing <b>{chunks.length}</b> of <b>{chunksTotal}</b>
                </div>
              )}
              {isTreeCollection && treeData && (
                <div className="mini" style={{ marginLeft: "auto" }}>
                  Nodes <b>{countNodes(treeData)}</b> | Leaves{" "}
                  <b>{countLeaves(treeData)}</b>
                </div>
              )}
            </div>

            {/* ── Loading state — inside results area ── */}
            {(isTreeCollection ? treeLoading : chunksLoading) && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: "48px 0",
                  gap: 12,
                }}
              >
                <div
                  className="btnSpinner"
                  style={{ width: 28, height: 28, borderWidth: 3 }}
                />
                <span style={{ color: "var(--c-text-muted)", fontSize: 13 }}>
                  {isTreeCollection ? "Loading tree…" : "Searching chunks…"}
                </span>
              </div>
            )}

            {/* ── Empty state ── */}
            {!treeLoading && isTreeCollection && treeError && (
              <div className="treeEmptyState">{treeError}</div>
            )}

            {!chunksLoading && !isTreeCollection && chunks.length === 0 && (
              <div
                style={{
                  textAlign: "center",
                  padding: "40px 0",
                  color: "var(--c-text-muted)",
                  fontSize: 13,
                }}
              >
                No chunks found. Adjust filters and press Search.
              </div>
            )}

            {!treeLoading && isTreeCollection && !treeError && !treeData && (
              <div className="treeEmptyState">
                No tree found for this collection. Re-upload with Tree Index.
              </div>
            )}

            {!treeLoading && isTreeCollection && treeData && (
              <div className="treeList">{renderTreeNode(treeData, 0)}</div>
            )}

            {/* ── Results ── */}
            {!chunksLoading && !isTreeCollection && chunks.length > 0 && (
              <>
                <div className="chunkList">
                  {chunks.map((c) => (
                    <div key={c.id} className="chunkCard">
                      {c.chunk_text?.startsWith("[Image") && (
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 4,
                            background: "#f59e0b22",
                            color: "#f59e0b",
                            borderRadius: 4,
                            padding: "2px 7px",
                            fontSize: 11,
                            fontWeight: 600,
                            marginBottom: 6,
                          }}
                        >
                          <Image size={10} /> Image chunk
                        </span>
                      )}
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
                        {highlightChunkText(
                          c.chunk_text?.length > 400
                            ? c.chunk_text.slice(0, 400) + "..."
                            : c.chunk_text || "",
                          chunkQuery,
                        )}
                      </div>
                      <button
                        className="btn"
                        style={{ marginTop: 6 }}
                        onClick={() => {
                          if (!collectionFiles.length) fetchCollectionFiles();
                          setShowPdfViewer(true);
                          openPdfInViewer({
                            fileId: c.file_id,
                            page: c.page_number ?? 0,
                          });
                        }}
                      >
                        Open PDF @ Page {c.page_number ?? 0}
                      </button>
                    </div>
                  ))}
                </div>

                <div className="chunkPager" style={{ marginTop: 12 }}>
                  <button
                    className="btn"
                    disabled={chunkOffset <= 0}
                    onClick={() =>
                      setChunkOffset((o) => Math.max(0, o - chunkLimit))
                    }
                  >
                    Prev
                  </button>
                  <div className="mini" style={{ margin: "0 10px" }}>
                    Page {Math.floor(chunkOffset / chunkLimit) + 1} of{" "}
                    {Math.ceil(chunksTotal / chunkLimit)}
                  </div>
                  <button
                    className="btn"
                    disabled={chunkOffset + chunkLimit >= chunksTotal}
                    onClick={() => setChunkOffset((o) => o + chunkLimit)}
                  >
                    Next
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    );
  };

  /* ── Active Panel Router ── */
  const renderActivePanel = () => {
    switch (activeTool) {
      case "chat":
      case "fast":
      case "compare":
        return ChatThreadView();
      case "image":
        return ImageTestPanel();
      case "config":
        return PipelineConfigPanel();
      case "leaderboard":
        return LeaderboardPanel();
      case "chunks":
        return ChunkExplorerPanel();
      default:
        return ChatThreadView();
    }
  };

  // --------------------------------
  // Claude-style Render
  // --------------------------------

  // Auth loading state
  if (authLoading) {
    return (
      <div className="authGate">
        <div className="authCard">
          <div className="spinnerLg" />
          <div className="mini" style={{ marginTop: 16 }}>
            Loading...
          </div>
        </div>
      </div>
    );
  }

  // Show about page if requested
  if (showAbout) {
    return <About onBack={() => setShowAbout(false)} />;
  }

  // Show documentation page if requested
  if (showDocumentation) {
    return <Documentation onBack={() => setShowDocumentation(false)} />;
  }

  // Auth gate — must sign in
  if (!user) {
    return (
      <div
        style={{
          display: "flex",
          height: "100vh",
          width: "100vw",
          background:
            "linear-gradient(180deg, rgba(15,15,18,0.75), rgba(15,15,18,0.95))",
          backgroundColor: "#0F0F12",
          color: "#E6E6E6",
          position: "relative",
          overflow: "hidden",
          fontFamily: "'Inter', sans-serif",
        }}
      >
        {/* Animated Background */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            zIndex: 0,
          }}
        >
          <Silk
            speed={5}
            scale={1}
            color="#8556ae"
            noiseIntensity={1.5}
            rotation={0}
          />
        </div>

        <div
          style={{
            position: "relative",
            zIndex: 10,
            display: "flex",
            flexDirection: "row",
            width: "100%",
            height: "100%",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 8%",
            boxSizing: "border-box",
          }}
        >
          {/* Left Info Panel */}
          <div
            style={{
              background: "rgba(20, 20, 28, 0.55)",
              backdropFilter: "blur(12px)",
              WebkitBackdropFilter: "blur(12px)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: "16px",
              padding: "40px",
              width: "520px",
              display: "flex",
              flexDirection: "column",
              boxSizing: "border-box",
            }}
          >
            <h1
              style={{
                fontFamily: "'Space Grotesk', sans-serif",
                fontSize: "56px",
                fontWeight: 700,
                lineHeight: 1.1,
                margin: "0 0 20px 0",
                color: "#fff",
                letterSpacing: "-0.02em",
              }}
            >
              Optimize and Benchmark Your RAG Pipelines
            </h1>
            <p
              style={{
                fontSize: "18px",
                color: "#9CA3AF",
                lineHeight: 1.5,
                margin: "0 0 32px 0",
                fontWeight: 400,
              }}
            >
              Compare retrieval strategies, measure latency, evaluate
              groundedness, and export performance reports.
            </p>
            <ul
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                display: "flex",
                flexDirection: "column",
                gap: "16px",
              }}
            >
              {[
                "Multi-Pipeline Benchmarking",
                "Latency & Cost Analytics",
                "Vector + Page Index Retrieval",
                "Multi-Model Testing",
                "Export Reports (PDF, CSV, JSON)",
                "Pipeline Comparison Dashboard",
              ].map((ft, i) => (
                <li
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "12px",
                    fontSize: "15px",
                    color: "#E6E6E6",
                    fontWeight: 500,
                  }}
                >
                  <div
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      backgroundColor: "#FF7A59",
                    }}
                  />
                  {ft}
                </li>
              ))}
            </ul>
          </div>

          {/* Login Card */}
          <div
            style={{
              background: "rgba(26, 26, 31, 0.85)",
              backdropFilter: "blur(10px)",
              WebkitBackdropFilter: "blur(10px)",
              border: "1px solid #2A2A30",
              borderRadius: "16px",
              padding: "28px",
              width: "360px",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              textAlign: "center",
              boxSizing: "border-box",
            }}
          >
            <div
              style={{
                background: "rgba(255, 122, 89, 0.1)",
                padding: "32px",
                borderRadius: "50%",
                marginBottom: "20px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <img
                src="/logo.png"
                alt="RANGO"
                style={{ width: "96px", height: "96px" }}
              />
            </div>
            <h2
              style={{
                fontFamily: "'Space Grotesk', sans-serif",
                fontSize: "22px",
                margin: "0 0 8px 0",
                color: "#fff",
                fontWeight: 600,
              }}
            >
              RANGO
            </h2>
            <p
              style={{
                margin: "0 0 32px 0",
                color: "#9CA3AF",
                fontSize: "14px",
                fontWeight: 400,
              }}
            >
              RAG Pipeline Optimization Lab
            </p>

            <button
              onClick={signInWithGoogle}
              style={{
                width: "100%",
                height: "44px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "10px",
                background: "#FFFFFF",
                color: "#000000",
                border: "none",
                borderRadius: "10px",
                fontSize: "14px",
                fontWeight: 600,
                cursor: "pointer",
                transition: "transform 0.1s, box-shadow 0.1s",
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.transform = "translateY(-1px)";
                e.currentTarget.style.boxShadow =
                  "0 4px 20px rgba(255,122,89,0.2)";
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.transform = "translateY(0)";
                e.currentTarget.style.boxShadow = "none";
              }}
              onMouseDown={(e) =>
                (e.currentTarget.style.transform = "translateY(1px)")
              }
              onMouseUp={(e) =>
                (e.currentTarget.style.transform = "translateY(-1px)")
              }
            >
              <LogIn size={16} /> Sign in with Google
            </button>

            <p
              style={{
                marginTop: "24px",
                fontSize: "12px",
                color: "#6B7280",
                fontWeight: 400,
              }}
            >
              By signing in, you agree to Terms and Privacy Policy
            </p>

            <div
              style={{
                marginTop: "24px",
                display: "flex",
                gap: "20px",
                fontSize: "12px",
                fontWeight: 500,
              }}
            >
              <a 
                href="https://github.com/Rahul006-max/RANGO" 
                target="_blank" 
                rel="noopener noreferrer"
                style={{ color: "#9CA3AF", textDecoration: "none", cursor: "pointer" }}
                onMouseOver={(e) => e.target.style.color = "#fff"}
                onMouseOut={(e) => e.target.style.color = "#9CA3AF"}
              >
                GitHub
              </a>
              <button 
                onClick={() => setShowDocumentation(true)}
                style={{ 
                  background: "none", 
                  border: "none", 
                  color: "#9CA3AF", 
                  cursor: "pointer", 
                  fontSize: "12px",
                  fontWeight: 500,
                  padding: "0",
                  fontFamily: "inherit",
                  textDecoration: "none",
                }}
                onMouseOver={(e) => e.target.style.color = "#fff"}
                onMouseOut={(e) => e.target.style.color = "#9CA3AF"}
              >
                Documentation
              </button>
              <button 
                onClick={() => setShowAbout(true)}
                style={{ 
                  background: "none", 
                  border: "none", 
                  color: "#9CA3AF", 
                  cursor: "pointer", 
                  fontSize: "12px",
                  fontWeight: 500,
                  padding: "0",
                  fontFamily: "inherit",
                  textDecoration: "none",
                }}
                onMouseOver={(e) => e.target.style.color = "#fff"}
                onMouseOut={(e) => e.target.style.color = "#9CA3AF"}
              >
                About
              </button>
            </div>
          </div>
        </div>

        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              borderRadius: 12,
              fontFamily: "'Inter', sans-serif",
              fontSize: 13,
              background: "#1A1A1F",
              color: "#fff",
              border: "1px solid #2A2A30",
            },
          }}
        />
      </div>
    );
  }

  return (
    <div className={`claudeShell ${rightPanelOpen ? "withRightPanel" : ""}`}>
      {/* ── Sidebar ── */}
      <aside
        className={`claudeSidebar${sidebarOpen ? "" : " sidebarCollapsed"}`}
      >
        <div className="sidebarTop">
          <div className="sidebarTopRow">
            <div className="sidebarLogo">RAG Optimizer</div>
            <button
              className="sidebarCollapseBtn"
              onClick={() => setSidebarOpen(false)}
              title="Collapse sidebar"
              aria-label="Collapse sidebar"
            >
              <PanelLeftClose size={15} />
            </button>
          </div>
          <button
            className="sidebarNewBtn"
            onClick={() => {
              setForceNewCollection(true);
              setShowUploadModal(true);
              setUploadRes(null);
              setFiles([]);
            }}
            title="New collection"
            aria-label="New collection"
          >
            <Plus size={15} />
            <span>New collection</span>
          </button>
        </div>

        {SidebarCollections()}

        <div className="toolStrip">
          {[
            { key: "chat", icon: <MessageSquare size={18} />, label: "Chat" },
            { key: "image", icon: <Image size={18} />, label: "Image" },
            { key: "config", icon: <Settings size={18} />, label: "Config" },
            { key: "leaderboard", icon: <Trophy size={18} />, label: "Stats" },
            {
              key: "chunks",
              icon: <Search size={18} />,
              label: activeCollectionIndexType === "tree" ? "Tree" : "Chunks",
            },
          ].map((t) => (
            <button
              key={t.key}
              className={`toolIcon ${activeTool === t.key ? "active" : ""}`}
              onClick={() => {
                setActiveTool(t.key);
                if (t.key === "chunks") {
                  setChunkExplorerOpen(true);
                  setChunkOffset(0);
                  if (activeCollectionIndexType !== "tree") {
                    fetchChunks();
                  }
                }
                if (t.key === "config") fetchCustomPipeline();
                if (t.key === "leaderboard") fetchLeaderboard();
              }}
              title={t.label}
              aria-label={t.label}
            >
              {t.icon}
              <span className="toolTip">{t.label}</span>
            </button>
          ))}
        </div>

        <div className="sidebarUser">
          <div className="sidebarAvatar">
            {user.email?.[0]?.toUpperCase() || "U"}
          </div>
          <div className="sidebarUserName">
            {user.user_metadata?.full_name ||
              user.user_metadata?.name ||
              user.email?.split("@")[0] ||
              "User"}
          </div>
          <button
            className="toolIcon"
            onClick={() => setModelSelectionOpen(true)}
            title="Select model"
            aria-label="Select model"
          >
            <Sparkles size={16} />
          </button>
          <button
            className="toolIcon"
            onClick={() => setDarkMode((d) => !d)}
            title="Toggle theme"
            aria-label="Toggle theme"
          >
            {darkMode ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          <button
            className="toolIcon signOutBtn"
            onClick={signOut}
            title="Sign out"
            aria-label="Sign out"
          >
            <LogOut size={16} />
          </button>
        </div>
      </aside>

      {/* ── Main Area ── */}
      <main className="claudeMain">
        <div className="claudeTopbar">
          {!sidebarOpen && (
            <button
              className="sidebarReopenBtn"
              onClick={() => setSidebarOpen(true)}
              title="Open sidebar"
              aria-label="Open sidebar"
            >
              <PanelLeftOpen size={16} />
            </button>
          )}
          <div className="topbarTitle">
            {activeTool === "chat" ||
            activeTool === "fast" ||
            activeTool === "compare"
              ? activeCollectionName || "Select a collection"
              : activeTool === "image"
                ? "Image Analysis"
                : activeTool === "config"
                  ? "Pipeline Configuration"
                  : activeTool === "leaderboard"
                    ? "Leaderboard"
                    : activeTool === "chunks"
                      ? activeCollectionIndexType === "tree"
                        ? "Tree Explorer"
                        : "Chunk Explorer"
                      : "RAG Optimizer"}
          </div>
          <div className="topbarActions">
            {collectionId && (
              <span className="mini" style={{ opacity: 0.7 }}>
                {collectionId.slice(0, 8)}
              </span>
            )}
            <button
              className={`toolIcon ${rightPanelOpen ? "active" : ""}`}
              onClick={() => {
                setRightPanelOpen((o) => !o);
                if (!rightPanelOpen) fetchLeaderboard();
              }}
              title="Analytics panel"
              aria-label="Analytics panel"
            >
              <BarChart3 size={18} />
            </button>
          </div>
        </div>

        <div className="claudeBody">
          {error && (
            <div
              className="topError"
              style={{
                margin: "0 0 12px",
                padding: "10px 16px",
                background: "var(--c-danger-bg, #ffe1e1)",
                color: "var(--c-danger, #d9534f)",
                borderRadius: 10,
                fontSize: 13,
              }}
            >
              {error}
            </div>
          )}
          {renderActivePanel()}
        </div>
      </main>

      {/* ── Right Panel (Analytics + Leaderboard) ── */}
      {rightPanelOpen && (
        <aside className="claudeRightPanel">
          <div className="rightPanelHeader">
            <span className="rightPanelTitle">
              <BarChart3 size={16} style={{ marginRight: 6 }} /> Analytics
            </span>
            <button
              className="toolIcon"
              onClick={() => setRightPanelOpen(false)}
              aria-label="Close panel"
            >
              <X size={16} />
            </button>
          </div>
          <div className="rightPanelBody">
            {/* Chat Session Summary — only in chat mode */}
            {mode === "chat" &&
              Object.keys(chatAnalytics).length > 0 &&
              (() => {
                const entries = Object.values(chatAnalytics);
                const avgLatency = Math.round(
                  entries.reduce((s, e) => s + (e.latency_ms || 0), 0) /
                    entries.length,
                );
                const pipelineCounts = entries.reduce((acc, e) => {
                  acc[e.pipeline] = (acc[e.pipeline] || 0) + 1;
                  return acc;
                }, {});
                const topPipeline =
                  Object.entries(pipelineCounts).sort(
                    (a, b) => b[1] - a[1],
                  )[0]?.[0] || "N/A";
                const smartCount = entries.filter(
                  (e) => e.smart_extract,
                ).length;
                return (
                  <div className="rpSection">
                    <div className="rpSectionTitle">
                      <MessageSquare size={14} style={{ marginRight: 6 }} />{" "}
                      Chat Session
                    </div>
                    <div className="rpStats">
                      <div className="rpStat">
                        <div className="rpStatLabel">Turns</div>
                        <div className="rpStatValue">{entries.length}</div>
                      </div>
                      <div className="rpStat">
                        <div className="rpStatLabel">Avg Latency</div>
                        <div className="rpStatValue">{avgLatency} ms</div>
                      </div>
                      <div className="rpStat">
                        <div className="rpStatLabel">Smart Extracts</div>
                        <div className="rpStatValue">{smartCount}</div>
                      </div>
                    </div>
                    <div
                      className="mini"
                      style={{ marginTop: 8, fontWeight: 600 }}
                    >
                      Top Pipeline
                    </div>
                    <div
                      style={{
                        fontSize: 13,
                        marginTop: 4,
                        color: "var(--c-accent)",
                        fontWeight: 500,
                      }}
                    >
                      {topPipeline}
                    </div>
                  </div>
                );
              })()}

            {/* Fast/Compare Mode Analysis — show all analytics in side panel */}
            {(mode === "fast" || mode === "compare") && askRes && (
              <div style={{ marginTop: 16 }}>
                {mode === "compare" ? (
                  <DetailedMetricsPanel
                    result={askRes}
                    retrieval_comparison={askRes.retrieval_comparison}
                  />
                ) : (
                  <div style={{ padding: "0 10px" }}>
                    <ResultsDashboard />
                  </div>
                )}
              </div>
            )}

            {/* This Chat's Ranking — ranked by composite score: docs retrieved, latency, smart cache */}
            {mode === "chat" &&
              Object.keys(chatAnalytics).length > 0 &&
              (() => {
                const pipeAgg = {};
                Object.values(chatAnalytics).forEach((e) => {
                  if (!e.pipeline) return;
                  if (!pipeAgg[e.pipeline]) {
                    pipeAgg[e.pipeline] = {
                      pipeline: e.pipeline,
                      uses: 0,
                      totalLatency: 0,
                      totalDocs: 0,
                      smartCount: 0,
                    };
                  }
                  pipeAgg[e.pipeline].uses += 1;
                  pipeAgg[e.pipeline].totalLatency += e.latency_ms || 0;
                  pipeAgg[e.pipeline].totalDocs += e.docs_retrieved || 0;
                  if (e.smart_extract) pipeAgg[e.pipeline].smartCount += 1;
                });
                const ranked = Object.values(pipeAgg)
                  .map((p) => ({
                    ...p,
                    avgLatency: Math.round(p.totalLatency / p.uses),
                    avgDocs: Math.round(p.totalDocs / p.uses),
                    smartRate: p.smartCount / p.uses,
                  }))
                  .map((p) => ({
                    ...p,
                    score:
                      p.avgDocs * 10 -
                      p.avgLatency / 100 +
                      (1 - p.smartRate) * 5,
                  }))
                  .sort((a, b) => b.score - a.score);
                return (
                  <div className="rpSection">
                    <div className="rpSectionTitle">
                      <Trophy size={14} style={{ marginRight: 6 }} /> This
                      Chat's Ranking
                    </div>
                    {ranked.map((p, i) => (
                      <div
                        key={i}
                        className={`rpPipeRow ${i === 0 ? "winner" : ""}`}
                      >
                        <div
                          className="rpPipeRank"
                          style={{ fontSize: 12, fontWeight: 600 }}
                        >
                          #{i + 1}
                        </div>
                        <div className="rpPipeInfo">
                          <div className="rpPipeName">{p.pipeline}</div>
                          <div className="mini">
                            {p.avgLatency} ms · {p.avgDocs} docs · {p.uses} turn
                            {p.uses !== 1 ? "s" : ""}
                            {p.smartCount > 0 && ` · ${p.smartCount} cached`}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })()}

            {/* Global Leaderboard Summary */}
            {leaderboard && (
              <div className="rpSection">
                <div
                  className="rpSectionTitle"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <span>
                    <BarChart3 size={14} style={{ marginRight: 6 }} /> Overall
                    Stats
                  </span>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      className="btn"
                      style={{ fontSize: 11, padding: "2px 8px" }}
                      onClick={downloadAnalyticsPDF}
                      title="Download as PDF"
                    >
                      <Download size={11} />
                    </button>
                    <button
                      className="btn"
                      style={{ fontSize: 11, padding: "2px 8px" }}
                      onClick={fetchLeaderboard}
                      disabled={leaderboardLoading}
                    >
                      {leaderboardLoading ? (
                        <span className="btnSpinner" />
                      ) : (
                        <RefreshCw size={11} />
                      )}
                    </button>
                  </div>
                </div>
                <div className="rpStats">
                  <div className="rpStat">
                    <div className="rpStatLabel">Questions</div>
                    <div className="rpStatValue">
                      {leaderboard.total_questions}
                    </div>
                  </div>
                  <div className="rpStat">
                    <div className="rpStatLabel">Best Today</div>
                    <div className="rpStatValue">
                      {leaderboard.best_pipeline_today || "N/A"}
                    </div>
                  </div>
                </div>
                {leaderboard.pipelines?.slice(0, 3).map((p, i) => {
                  const label = `Pipeline ${i + 1}`;
                  const scoreDisplay =
                    p.leaderboard_score != null
                      ? `${(p.leaderboard_score * 100).toFixed(1)}%`
                      : p.avg_final_score;
                  return (
                    <div
                      key={i}
                      className={`rpPipeRow ${i === 0 ? "winner" : ""}`}
                    >
                      <div
                        className="rpPipeRank"
                        style={{ fontSize: 12, fontWeight: 600 }}
                      >
                        {label}
                      </div>
                      <div className="rpPipeInfo">
                        <div className="rpPipeName">{p.pipeline}</div>
                        <div className="mini">
                          {scoreDisplay} · W: {p.wins} (
                          {(p.win_rate * 100).toFixed(1)}%)
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </aside>
      )}

      {/* Upload Modal */}
      {showUploadModal && UploadModal()}

      {/* Rename Modal */}
      {renameModalOpen && (
        <div className="customModal" onClick={() => setRenameModalOpen(false)}>
          <div className="customModalCard" onClick={(e) => e.stopPropagation()}>
            <div className="customModalTitle">Rename Collection</div>
            <div className="customModalBody">
              <input
                type="text"
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                placeholder="New name"
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  borderRadius: 8,
                  border: "1px solid var(--c-border)",
                  background: "var(--c-surface)",
                  color: "var(--c-text)",
                  fontSize: 14,
                }}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter") renameCollection(renameTarget);
                }}
              />
            </div>
            <div className="customModalActions">
              <button className="btn" onClick={() => setRenameModalOpen(false)}>
                Cancel
              </button>
              <button
                className="btn primary"
                onClick={() => renameCollection(renameTarget)}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Modal */}
      {deleteModalOpen && (
        <div className="customModal" onClick={() => setDeleteModalOpen(false)}>
          <div className="customModalCard" onClick={(e) => e.stopPropagation()}>
            <div className="customModalTitle">Delete Collection</div>
            <div className="customModalBody">
              <p
                style={{
                  margin: 0,
                  fontSize: 14,
                  color: "var(--c-text-secondary)",
                }}
              >
                This will permanently delete the collection and all its data.
                This action cannot be undone.
              </p>
            </div>
            <div className="customModalActions">
              <button
                className="btn"
                onClick={() => {
                  setDeleteModalOpen(false);
                  setDeleteTarget(null);
                }}
                disabled={deletingCollection}
              >
                Cancel
              </button>
              <button
                className="btn danger"
                onClick={() => deleteCollection(deleteTarget)}
                disabled={deletingCollection}
              >
                {deletingCollection ? (
                  <>
                    <span
                      className="btnSpinner"
                      style={{ borderTopColor: "#fff" }}
                    />
                    &nbsp;Deleting...
                  </>
                ) : (
                  "Delete"
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Clear Chat Modal */}
      {clearChatModalOpen && (
        <div
          className="customModal"
          onClick={() => setClearChatModalOpen(false)}
        >
          <div className="customModalCard" onClick={(e) => e.stopPropagation()}>
            <div className="customModalTitle">Clear Chat History</div>
            <div className="customModalBody">
              <p
                style={{
                  margin: 0,
                  fontSize: 14,
                  color: "var(--c-text-secondary)",
                }}
              >
                This will delete all messages in the current chat. Continue?
              </p>
            </div>
            <div className="customModalActions">
              <button
                className="btn"
                onClick={() => setClearChatModalOpen(false)}
              >
                Cancel
              </button>
              <button className="btn danger" onClick={clearChat}>
                Clear
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Model Selection & Management Modal */}
      {modelSelectionOpen && availableModels.length > 0 && (
        <div
          className="customModal"
          onClick={() => setModelSelectionOpen(false)}
        >
          <div className="customModalCard" onClick={(e) => e.stopPropagation()}>
            <div className="customModalTitle">
              {addModelMode && editingModelId
                ? "Edit Custom Model"
                : addModelMode
                  ? "Add Custom Model"
                  : "Select Your AI Model"}
            </div>
            <div className="customModalBody">
              {!addModelMode ? (
                <>
                  <p
                    style={{
                      marginBottom: 20,
                      fontSize: "clamp(13px, 3vw, 14px)",
                      color: "var(--c-text-secondary)",
                      lineHeight: 1.6,
                    }}
                  >
                    Choose which AI model to use for your RAG queries:
                  </p>
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: 10,
                      marginBottom: 20,
                    }}
                  >
                    {availableModels.map((model) => (
                      <div
                        key={model.id}
                        onClick={() => setActiveModel(model.id)}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 12,
                          padding: "14px 16px",
                          borderRadius: 10,
                          border:
                            selectedModel === model.id
                              ? "2px solid var(--c-accent)"
                              : "1px solid var(--c-border)",
                          background:
                            selectedModel === model.id
                              ? "var(--c-accent-dim)"
                              : "var(--c-surface)",
                          minHeight: "52px",
                          transition: "all 0.2s ease",
                          cursor: "pointer",
                        }}
                      >
                        <div
                          style={{
                            flex: 1,
                            textAlign: "left",
                            display: "flex",
                            flexDirection: "column",
                            gap: 4,
                            justifyContent: "center",
                          }}
                        >
                          <div
                            style={{
                              fontWeight: 600,
                              fontSize: "clamp(14px, 3vw, 15px)",
                            }}
                          >
                            {model.model_name}
                          </div>
                          <div
                            style={{
                              fontSize: "clamp(12px, 2.5vw, 13px)",
                              color: "var(--c-text-secondary)",
                            }}
                          >
                            {model.provider || "System Default"}
                            {model.is_active && " • Active"}
                          </div>
                        </div>
                        {model.is_custom && (
                          <div
                            style={{
                              display: "flex",
                              gap: 8,
                              alignItems: "center",
                            }}
                          >
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                e.preventDefault();
                                startEditModel(model);
                              }}
                              style={{
                                padding: "8px 12px",
                                fontSize: "clamp(12px, 2.5vw, 13px)",
                                borderRadius: 6,
                                border: "1px solid var(--c-border)",
                                background: "var(--c-surface)",
                                color: "var(--c-text-secondary)",
                                cursor: "pointer",
                                transition: "all 0.2s",
                                minHeight: "36px",
                                minWidth: "60px",
                                fontWeight: 500,
                              }}
                              title="Edit custom model"
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                e.preventDefault();
                                deleteCustomModel(model.id);
                              }}
                              style={{
                                padding: "8px 12px",
                                fontSize: "clamp(12px, 2.5vw, 13px)",
                                borderRadius: 6,
                                border: "1px solid var(--c-border)",
                                background: "var(--c-surface)",
                                color: "var(--c-text-secondary)",
                                cursor: "pointer",
                                transition: "all 0.2s",
                                minHeight: "36px",
                                minWidth: "70px",
                                fontWeight: 500,
                              }}
                              title="Delete custom model"
                            >
                              Delete
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                  <button
                    onClick={startAddModel}
                    style={{
                      width: "100%",
                      padding: "14px 16px",
                      borderRadius: 10,
                      border: "2px dashed var(--c-border)",
                      background: "transparent",
                      color: "var(--c-accent)",
                      fontWeight: 600,
                      cursor: "pointer",
                      transition: "all 0.2s",
                      fontSize: "clamp(14px, 3vw, 15px)",
                      minHeight: "44px",
                    }}
                  >
                    + Add Custom Model
                  </button>
                </>
              ) : (
                <>
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: 16,
                    }}
                  >
                    <div>
                      <label
                        style={{
                          fontSize: "clamp(12px, 3vw, 13px)",
                          color: "var(--c-text-secondary)",
                          display: "block",
                          marginBottom: 6,
                          fontWeight: 500,
                        }}
                      >
                        Model Name
                      </label>
                      <input
                        type="text"
                        placeholder="e.g., My Ollama Model"
                        value={modelFormData.model_name}
                        onChange={(e) =>
                          setModelFormData({
                            ...modelFormData,
                            model_name: e.target.value,
                          })
                        }
                        style={{
                          width: "100%",
                          padding: "10px 14px",
                          borderRadius: 8,
                          border: "1px solid var(--c-border)",
                          background: "var(--c-surface)",
                          color: "var(--c-text)",
                          fontSize: "clamp(14px, 3vw, 15px)",
                          boxSizing: "border-box",
                          minHeight: "44px",
                          transition: "border-color 0.2s",
                        }}
                      />
                    </div>

                    <div>
                      <label
                        style={{
                          fontSize: "clamp(12px, 3vw, 13px)",
                          color: "var(--c-text-secondary)",
                          display: "block",
                          marginBottom: 6,
                          fontWeight: 500,
                        }}
                      >
                        Provider
                      </label>
                      <select
                        value={modelFormData.provider}
                        onChange={(e) =>
                          setModelFormData({
                            ...modelFormData,
                            provider: e.target.value,
                          })
                        }
                        style={{
                          width: "100%",
                          padding: "10px 14px",
                          borderRadius: 8,
                          border: "1px solid var(--c-border)",
                          background: "var(--c-surface)",
                          color: "var(--c-text)",
                          fontSize: "clamp(14px, 3vw, 15px)",
                          boxSizing: "border-box",
                          minHeight: "44px",
                          cursor: "pointer",
                          transition: "border-color 0.2s",
                        }}
                      >
                        <option value="groq">Groq API</option>
                        <option value="ollama">Ollama (Local)</option>
                        <option value="openai">OpenAI API</option>
                        <option value="anthropic">Anthropic Claude</option>
                        <option value="custom">Custom API Endpoint</option>
                      </select>
                    </div>

                    <div>
                      <label
                        style={{
                          fontSize: "clamp(12px, 3vw, 13px)",
                          color: "var(--c-text-secondary)",
                          display: "block",
                          marginBottom: 6,
                          fontWeight: 500,
                        }}
                      >
                        API URL or Endpoint
                      </label>
                      <input
                        type="text"
                        placeholder={
                          modelFormData.provider === "ollama"
                            ? "http://localhost:11434"
                            : modelFormData.provider === "groq"
                              ? "https://api.groq.com/openai/v1"
                              : "https://api.openai.com/v1"
                        }
                        value={modelFormData.api_url}
                        onChange={(e) =>
                          setModelFormData({
                            ...modelFormData,
                            api_url: e.target.value,
                          })
                        }
                        style={{
                          width: "100%",
                          padding: "10px 14px",
                          borderRadius: 8,
                          border: "1px solid var(--c-border)",
                          background: "var(--c-surface)",
                          color: "var(--c-text)",
                          fontSize: "clamp(14px, 3vw, 15px)",
                          boxSizing: "border-box",
                          minHeight: "44px",
                          transition: "border-color 0.2s",
                        }}
                      />
                    </div>

                    <div>
                      <label
                        style={{
                          fontSize: "clamp(12px, 3vw, 13px)",
                          color: "var(--c-text-secondary)",
                          display: "block",
                          marginBottom: 6,
                          fontWeight: 500,
                        }}
                      >
                        API Key
                      </label>
                      <input
                        type="password"
                        placeholder="sk-... or your API key"
                        value={modelFormData.api_key}
                        onChange={(e) =>
                          setModelFormData({
                            ...modelFormData,
                            api_key: e.target.value,
                          })
                        }
                        style={{
                          width: "100%",
                          padding: "10px 14px",
                          borderRadius: 8,
                          border: "1px solid var(--c-border)",
                          background: "var(--c-surface)",
                          color: "var(--c-text)",
                          fontSize: "clamp(14px, 3vw, 15px)",
                          boxSizing: "border-box",
                          minHeight: "44px",
                          transition: "border-color 0.2s",
                        }}
                      />
                    </div>

                    <div>
                      <label
                        style={{
                          fontSize: "clamp(12px, 3vw, 13px)",
                          color: "var(--c-text-secondary)",
                          display: "block",
                          marginBottom: 6,
                          fontWeight: 500,
                        }}
                      >
                        Temperature ({modelFormData.temperature})
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="2"
                        step="0.1"
                        value={modelFormData.temperature}
                        onChange={(e) =>
                          setModelFormData({
                            ...modelFormData,
                            temperature: parseFloat(e.target.value),
                          })
                        }
                        style={{
                          width: "100%",
                          cursor: "pointer",
                          height: 6,
                          minHeight: "44px",
                          padding: "19px 0",
                        }}
                      />
                      <div
                        style={{
                          fontSize: "clamp(11px, 2.5vw, 12px)",
                          color: "var(--c-text-secondary)",
                          marginTop: 6,
                          lineHeight: 1.4,
                        }}
                      >
                        Lower = more focused, Higher = more creative (0-2)
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
            <div className="customModalActions">
              {addModelMode ? (
                <>
                  <button
                    className="btn"
                    onClick={editingModelId ? cancelEditModel : cancelAddModel}
                    disabled={savingModel || testingConnectivity}
                  >
                    Cancel
                  </button>
                  <button
                    className="btn"
                    onClick={testModelConnectivity}
                    disabled={savingModel || testingConnectivity}
                  >
                    {testingConnectivity ? (
                      <>
                        <span
                          className="btnSpinner"
                          style={{ borderTopColor: "currentColor" }}
                        />
                        &nbsp;Testing...
                      </>
                    ) : (
                      "Test Connection"
                    )}
                  </button>
                  <button
                    className="btn primary"
                    onClick={editingModelId ? editCustomModel : addCustomModel}
                    disabled={savingModel || testingConnectivity}
                  >
                    {savingModel ? (
                      <>
                        <span
                          className="btnSpinner"
                          style={{ borderTopColor: "#fff" }}
                        />
                        &nbsp;{editingModelId ? "Updating..." : "Saving..."}
                      </>
                    ) : editingModelId ? (
                      "Update Model"
                    ) : (
                      "Save Model"
                    )}
                  </button>
                </>
              ) : (
                <button
                  className="btn primary"
                  onClick={() => setModelSelectionOpen(false)}
                >
                  Done
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      <Toaster
        position="top-right"
        toastOptions={{
          duration: 3000,
          style: {
            border: "1px solid var(--c-border, #e0e0e0)",
            borderRadius: 12,
            boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
            fontFamily: "var(--font-sans)",
            fontWeight: 500,
            fontSize: 13,
            padding: "10px 16px",
            maxWidth: 420,
            background: "#fff",
            color: "#000",
          },
          success: {
            duration: 3000,
            style: {
              background: "#d4edda",
              color: "#155724",
            },
          },
          error: {
            duration: 5000,
            style: {
              background: "#ffe1e1",
              color: "#721c24",
            },
          },
          loading: {
            style: {
              background: "#f5f5f0",
              color: "#000",
            },
          },
        }}
      />
    </div>
  );
}
