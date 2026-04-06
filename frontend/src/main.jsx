import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import App from "./App.jsx";

try {
  const root = ReactDOM.createRoot(document.getElementById("root"));
  root.render(<App />);
} catch (error) {
  console.error("Failed to render app:", error);
  document.getElementById("root").innerHTML = `<h1>Error: ${error.message}</h1><pre>${error.stack}</pre>`;
}
