import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api/v1",
  timeout: 120000,
});

export async function healthCheck() {
  const { data } = await api.get("/health");
  return data;
}

export async function listDatasets() {
  const { data } = await api.get("/datasets");
  return data;
}

export async function uploadDataset(file) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post("/datasets/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getDataset(datasetId) {
  const { data } = await api.get(`/datasets/${datasetId}`);
  return data;
}

export async function getDatasetProfile(datasetId) {
  const { data } = await api.get(`/datasets/${datasetId}/profile`);
  return data;
}

export async function detectIntent(query, datasetId) {
  const { data } = await api.post("/intent/detect", {
    query,
    dataset_id: datasetId || null,
  });
  return data;
}

export async function runAnalytics(payload) {
  const { data } = await api.post("/analytics/query", payload);
  return data;
}

export async function createChart(payload) {
  const { data } = await api.post("/visualization/chart", payload);
  return data;
}

export function getErrorMessage(error) {
  return (
    error?.response?.data?.detail ||
    error?.message ||
    "Something went wrong talking to the API"
  );
}

export default api;
