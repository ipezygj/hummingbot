/**
 * Hummingbot API Client
 *
 * Typed client for communicating with the embedded Hummingbot FastAPI server.
 */

// Configuration
const DEFAULT_BASE_URL = "http://localhost:8000/api/v1";

let baseUrl = DEFAULT_BASE_URL;

export function setApiBaseUrl(url: string) {
  baseUrl = url;
}

export function getApiBaseUrl(): string {
  return baseUrl;
}

// Types
export interface APIResponse<T> {
  success: boolean;
  message?: string;
  data?: T;
  timestamp: string;
}

export interface AvailableConnector {
  name: string;
  display_name: string;
  connector_type: string;
  is_configured: boolean;
  trading_type?: string;
  required_credentials: string[];
}

export interface ConnectorBalance {
  asset: string;
  total: string;
  available: string;
  locked: string;
}

export interface ConnectorStatus {
  name: string;
  is_ready: boolean;
  status_dict: Record<string, boolean>;
  trading_pairs: string[];
  balances: ConnectorBalance[];
  error?: string;
}

export interface OrderInfo {
  order_id: string;
  client_order_id: string;
  connector_name: string;
  trading_pair: string;
  order_type: string;
  side: string;
  price?: string;
  amount: string;
  filled_amount: string;
  status: string;
  created_at?: string;
}

export interface PlaceOrderRequest {
  connector_name: string;
  trading_pair: string;
  side: "buy" | "sell";
  order_type: "limit" | "market";
  amount: string;
  price?: string;
}

export interface PositionInfo {
  connector_name: string;
  trading_pair: string;
  position_side: string;
  amount: string;
  entry_price: string;
  mark_price?: string;
  unrealized_pnl?: string;
  leverage?: number;
}

export interface MarketPrice {
  connector_name: string;
  trading_pair: string;
  mid_price: string;
  bid_price?: string;
  ask_price?: string;
}

export interface StrategyInfo {
  name: string;
  display_name: string;
  strategy_type: string;
  description?: string;
}

export interface StrategyStatus {
  is_running: boolean;
  strategy_name?: string;
  strategy_type?: string;
  runtime_seconds?: number;
  status_text?: string;
}

export interface ControllerConfig {
  id: string;
  controller_name: string;
  controller_type: string;
  connector_name?: string;
  trading_pair?: string;
  total_amount_quote?: string;
  manual_kill_switch: boolean;
  config: Record<string, unknown>;
}

export interface SystemHealth {
  status: string;
  application: string;
  timestamp: string;
}

export interface SystemInfo {
  version: string;
  python_version: string;
  platform: string;
  pid: number;
  timestamp: string;
}

// API Client
async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<APIResponse<T>> {
  const url = `${baseUrl}${endpoint}`;
  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  const response = await fetch(url, { ...options, headers });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `API error: ${response.status}`);
  }

  return response.json();
}

// System API
export const SystemAPI = {
  async health(): Promise<SystemHealth> {
    const res = await request<SystemHealth>("/health");
    return res.data!;
  },

  async info(): Promise<SystemInfo> {
    const res = await request<SystemInfo>("/info");
    return res.data!;
  },

  async status(): Promise<Record<string, unknown>> {
    const res = await request<Record<string, unknown>>("/status");
    return res.data!;
  },

  async getLogs(lines = 100, level?: string): Promise<string[]> {
    const params = new URLSearchParams({ lines: lines.toString() });
    if (level) params.append("level", level);
    const res = await request<string[]>(`/logs?${params}`);
    return res.data!;
  },
};

// Connectors API
export const ConnectorsAPI = {
  async list(): Promise<AvailableConnector[]> {
    const res = await request<AvailableConnector[]>("/connectors");
    return res.data!;
  },

  async getStatus(connectorName: string): Promise<ConnectorStatus> {
    const res = await request<ConnectorStatus>(`/connectors/${connectorName}/status`);
    return res.data!;
  },

  async getBalances(connectorName: string): Promise<ConnectorBalance[]> {
    const res = await request<ConnectorBalance[]>(`/connectors/${connectorName}/balances`);
    return res.data!;
  },

  async setCredentials(
    connectorName: string,
    credentials: Record<string, string>
  ): Promise<void> {
    await request(`/connectors/${connectorName}/credentials`, {
      method: "POST",
      body: JSON.stringify(credentials),
    });
  },
};

// Trading API
export const TradingAPI = {
  async listOrders(connectorName?: string, tradingPair?: string): Promise<OrderInfo[]> {
    const params = new URLSearchParams();
    if (connectorName) params.append("connector_name", connectorName);
    if (tradingPair) params.append("trading_pair", tradingPair);
    const query = params.toString() ? `?${params}` : "";
    const res = await request<OrderInfo[]>(`/trading/orders${query}`);
    return res.data!;
  },

  async placeOrder(order: PlaceOrderRequest): Promise<OrderInfo> {
    const res = await request<OrderInfo>("/trading/orders", {
      method: "POST",
      body: JSON.stringify(order),
    });
    return res.data!;
  },

  async cancelOrder(
    orderId: string,
    connectorName: string,
    tradingPair: string
  ): Promise<void> {
    const params = new URLSearchParams({
      connector_name: connectorName,
      trading_pair: tradingPair,
    });
    await request(`/trading/orders/${orderId}?${params}`, {
      method: "DELETE",
    });
  },

  async listPositions(connectorName?: string): Promise<PositionInfo[]> {
    const params = connectorName ? `?connector_name=${connectorName}` : "";
    const res = await request<PositionInfo[]>(`/trading/positions${params}`);
    return res.data!;
  },

  async getPrice(connectorName: string, tradingPair: string): Promise<MarketPrice> {
    const res = await request<MarketPrice>(
      `/trading/prices/${connectorName}/${tradingPair}`
    );
    return res.data!;
  },

  async getOrderbook(
    connectorName: string,
    tradingPair: string,
    depth = 10
  ): Promise<{ bids: { price: number; amount: number }[]; asks: { price: number; amount: number }[] }> {
    const res = await request<{ bids: { price: number; amount: number }[]; asks: { price: number; amount: number }[] }>(
      `/trading/orderbook/${connectorName}/${tradingPair}?depth=${depth}`
    );
    return res.data!;
  },
};

// Strategies API
export const StrategiesAPI = {
  async list(): Promise<StrategyInfo[]> {
    const res = await request<StrategyInfo[]>("/strategies");
    return res.data!;
  },

  async getStatus(): Promise<StrategyStatus> {
    const res = await request<StrategyStatus>("/strategies/status");
    return res.data!;
  },

  async start(scriptName?: string, strategyName?: string, config?: Record<string, unknown>): Promise<void> {
    await request("/strategies/start", {
      method: "POST",
      body: JSON.stringify({ script_name: scriptName, strategy_name: strategyName, config }),
    });
  },

  async stop(skipOrderCancellation = false): Promise<void> {
    await request(`/strategies/stop?skip_order_cancellation=${skipOrderCancellation}`, {
      method: "POST",
    });
  },

  async listConfigs(): Promise<string[]> {
    const res = await request<string[]>("/strategies/configs");
    return res.data!;
  },
};

// Controllers API
export const ControllersAPI = {
  async list(): Promise<ControllerConfig[]> {
    const res = await request<ControllerConfig[]>("/controllers");
    return res.data!;
  },

  async get(controllerId: string): Promise<ControllerConfig> {
    const res = await request<ControllerConfig>(`/controllers/${controllerId}`);
    return res.data!;
  },

  async create(
    controllerName: string,
    controllerType: string,
    config: Record<string, unknown>
  ): Promise<ControllerConfig> {
    const res = await request<ControllerConfig>("/controllers", {
      method: "POST",
      body: JSON.stringify({
        controller_name: controllerName,
        controller_type: controllerType,
        config,
      }),
    });
    return res.data!;
  },

  async update(controllerId: string, config: Record<string, unknown>): Promise<ControllerConfig> {
    const res = await request<ControllerConfig>(`/controllers/${controllerId}`, {
      method: "PUT",
      body: JSON.stringify({ config }),
    });
    return res.data!;
  },

  async delete(controllerId: string): Promise<void> {
    await request(`/controllers/${controllerId}`, {
      method: "DELETE",
    });
  },

  async listTypes(): Promise<{ type: string; description: string; examples: string[] }[]> {
    const res = await request<{ type: string; description: string; examples: string[] }[]>(
      "/controllers/types"
    );
    return res.data!;
  },
};

// Export all as single object
export const HummingbotAPI = {
  System: SystemAPI,
  Connectors: ConnectorsAPI,
  Trading: TradingAPI,
  Strategies: StrategiesAPI,
  Controllers: ControllersAPI,
  setBaseUrl: setApiBaseUrl,
  getBaseUrl: getApiBaseUrl,
};

export default HummingbotAPI;
