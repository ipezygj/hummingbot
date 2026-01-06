import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useApp } from "@/lib/AppContext";
import { HummingbotAPI, ConnectorBalance, ConnectorStatus, AvailableConnector } from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import { Plug, RefreshCw, Eye, EyeOff, Check, Plus, AlertCircle } from "lucide-react";
import { toast } from "sonner";

export function Connectors() {
  const { isConnected, connectors, refreshConnectors, selectedConnector, setSelectedConnector } = useApp();
  const [connectorStatus, setConnectorStatus] = useState<ConnectorStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [showCredentials, setShowCredentials] = useState(false);
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [savingCredentials, setSavingCredentials] = useState(false);
  const [addingNew, setAddingNew] = useState(false);

  const selectedConnectorInfo = connectors.find((c) => c.name === selectedConnector);

  const fetchConnectorStatus = async (connectorName: string) => {
    setLoading(true);
    try {
      const status = await HummingbotAPI.Connectors.getStatus(connectorName);
      setConnectorStatus(status);
    } catch (error) {
      console.error("Failed to fetch connector status:", error);
      setConnectorStatus(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedConnector && !addingNew) {
      fetchConnectorStatus(selectedConnector);
    }
  }, [selectedConnector, addingNew]);

  // Initialize credentials fields when selecting a connector for adding
  useEffect(() => {
    if (selectedConnectorInfo && addingNew) {
      const initialCreds: Record<string, string> = {};
      selectedConnectorInfo.required_credentials?.forEach((key) => {
        initialCreds[key] = "";
      });
      setCredentials(initialCreds);
    }
  }, [selectedConnectorInfo, addingNew]);

  const handleSaveCredentials = async () => {
    if (!selectedConnector) return;

    // Validate all fields are filled
    const emptyFields = Object.entries(credentials).filter(([, value]) => !value.trim());
    if (emptyFields.length > 0) {
      toast.error("Please fill in all credential fields");
      return;
    }

    setSavingCredentials(true);
    try {
      await HummingbotAPI.Connectors.setCredentials(selectedConnector, credentials);
      toast.success(`Credentials saved for ${selectedConnector}`);
      await refreshConnectors();
      setCredentials({});
      setShowCredentials(false);
      setAddingNew(false);
    } catch (error) {
      console.error("Failed to save credentials:", error);
      toast.error(`Failed to save credentials: ${error}`);
    } finally {
      setSavingCredentials(false);
    }
  };

  const handleAddConnector = (connector: AvailableConnector) => {
    setSelectedConnector(connector.name);
    setAddingNew(true);
    setShowCredentials(true);
    setConnectorStatus(null);
  };

  const handleCancelAdd = () => {
    setAddingNew(false);
    setCredentials({});
    setShowCredentials(false);
  };

  // Format credential key for display (e.g., "binance_api_key" -> "API Key")
  const formatCredentialLabel = (key: string): string => {
    // Remove connector prefix (e.g., "binance_api_key" -> "api_key")
    const parts = key.split("_");
    // Skip first part if it looks like a connector name
    const relevantParts = parts.length > 2 ? parts.slice(1) : parts;
    return relevantParts
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  };

  // Check if field should be hidden (contains "secret", "key", "password")
  const isSecretField = (key: string): boolean => {
    const lowerKey = key.toLowerCase();
    return lowerKey.includes("secret") || lowerKey.includes("password") || lowerKey.includes("private");
  };

  // Configured connectors (have credentials)
  const configuredConnectors = connectors.filter((c) => c.is_configured);
  // Available connectors (not yet configured)
  const availableConnectors = connectors.filter((c) => !c.is_configured);

  if (!isConnected) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] space-y-4">
        <Plug className="h-16 w-16 text-muted-foreground" />
        <h2 className="text-2xl font-semibold">Not Connected</h2>
        <p className="text-muted-foreground">Connect to Hummingbot to manage connectors</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Connectors</h1>
          <p className="text-muted-foreground">Manage your exchange connections</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refreshConnectors()}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left Column - Connector Lists */}
        <div className="space-y-6">
          {/* Configured Connectors */}
          <Card>
            <CardHeader>
              <CardTitle>Configured Connectors</CardTitle>
              <CardDescription>Connectors with saved credentials</CardDescription>
            </CardHeader>
            <CardContent>
              {configuredConnectors.length > 0 ? (
                <div className="space-y-2">
                  {configuredConnectors.map((connector) => (
                    <button
                      key={connector.name}
                      onClick={() => {
                        setSelectedConnector(connector.name);
                        setAddingNew(false);
                      }}
                      className={`w-full flex items-center justify-between p-3 rounded-lg border transition-colors ${
                        selectedConnector === connector.name && !addingNew
                          ? "border-primary bg-primary/5"
                          : "border-border hover:border-primary/50"
                      }`}
                    >
                      <div className="flex items-center space-x-3">
                        <div className="h-2 w-2 rounded-full bg-green-500" />
                        <div className="text-left">
                          <div className="font-medium">{connector.display_name}</div>
                          <div className="text-sm text-muted-foreground">{connector.connector_type}</div>
                        </div>
                      </div>
                      <Check className="h-5 w-5 text-green-500" />
                    </button>
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-8 text-center">
                  <AlertCircle className="h-8 w-8 text-muted-foreground mb-2" />
                  <p className="text-sm text-muted-foreground">No connectors configured yet</p>
                  <p className="text-xs text-muted-foreground mt-1">Add a connector below to get started</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Available Connectors */}
          <Card>
            <CardHeader>
              <CardTitle>Add Connector</CardTitle>
              <CardDescription>Select an exchange to add credentials</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 max-h-[300px] overflow-y-auto">
                {availableConnectors.map((connector) => (
                  <button
                    key={connector.name}
                    onClick={() => handleAddConnector(connector)}
                    className={`w-full flex items-center justify-between p-3 rounded-lg border transition-colors ${
                      selectedConnector === connector.name && addingNew
                        ? "border-primary bg-primary/5"
                        : "border-border hover:border-primary/50"
                    }`}
                  >
                    <div className="flex items-center space-x-3">
                      <div className="h-2 w-2 rounded-full bg-gray-400" />
                      <div className="text-left">
                        <div className="font-medium">{connector.display_name}</div>
                        <div className="text-sm text-muted-foreground">{connector.connector_type}</div>
                      </div>
                    </div>
                    <Plus className="h-5 w-5 text-muted-foreground" />
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column - Details/Add Form */}
        <div className="space-y-6">
          {addingNew && selectedConnectorInfo ? (
            /* Add Credentials Form */
            <Card>
              <CardHeader>
                <CardTitle>Add {selectedConnectorInfo.display_name}</CardTitle>
                <CardDescription>Enter your API credentials for {selectedConnectorInfo.display_name}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {selectedConnectorInfo.required_credentials?.length > 0 ? (
                    <>
                      {selectedConnectorInfo.required_credentials.map((credKey) => (
                        <div key={credKey} className="space-y-2">
                          <Label htmlFor={credKey}>{formatCredentialLabel(credKey)}</Label>
                          <div className="relative">
                            <Input
                              id={credKey}
                              type={isSecretField(credKey) && !showCredentials ? "password" : "text"}
                              placeholder={`Enter ${formatCredentialLabel(credKey).toLowerCase()}`}
                              value={credentials[credKey] || ""}
                              onChange={(e) =>
                                setCredentials({ ...credentials, [credKey]: e.target.value })
                              }
                            />
                            {isSecretField(credKey) && (
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="absolute right-0 top-0"
                                onClick={() => setShowCredentials(!showCredentials)}
                              >
                                {showCredentials ? (
                                  <EyeOff className="h-4 w-4" />
                                ) : (
                                  <Eye className="h-4 w-4" />
                                )}
                              </Button>
                            )}
                          </div>
                        </div>
                      ))}

                      <div className="flex space-x-2 pt-4">
                        <Button
                          onClick={handleSaveCredentials}
                          disabled={savingCredentials}
                          className="flex-1"
                        >
                          {savingCredentials ? "Saving..." : "Save Credentials"}
                        </Button>
                        <Button variant="outline" onClick={handleCancelAdd}>
                          Cancel
                        </Button>
                      </div>
                    </>
                  ) : (
                    <div className="text-center py-4">
                      <p className="text-muted-foreground">No credentials required for this connector</p>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ) : selectedConnector && !addingNew ? (
            /* Connector Status View */
            <>
              {/* Status Card */}
              <Card>
                <CardHeader>
                  <CardTitle>{selectedConnectorInfo?.display_name || selectedConnector}</CardTitle>
                  <CardDescription>
                    {loading ? "Loading..." : connectorStatus?.is_ready ? "Connected" : "Not Connected"}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {connectorStatus && (
                    <div className="space-y-4">
                      <div>
                        <Label className="text-sm text-muted-foreground">Trading Pairs</Label>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {connectorStatus.trading_pairs.length > 0 ? (
                            connectorStatus.trading_pairs.slice(0, 10).map((pair) => (
                              <span
                                key={pair}
                                className="inline-flex items-center rounded-md bg-muted px-2 py-1 text-xs"
                              >
                                {pair}
                              </span>
                            ))
                          ) : (
                            <span className="text-sm text-muted-foreground">No active trading pairs</span>
                          )}
                          {connectorStatus.trading_pairs.length > 10 && (
                            <span className="text-xs text-muted-foreground">
                              +{connectorStatus.trading_pairs.length - 10} more
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Balances Card */}
              <Card>
                <CardHeader>
                  <CardTitle>Balances</CardTitle>
                  <CardDescription>Your current balances on {selectedConnector}</CardDescription>
                </CardHeader>
                <CardContent>
                  {connectorStatus?.balances && connectorStatus.balances.length > 0 ? (
                    <div className="space-y-2">
                      {connectorStatus.balances.map((balance: ConnectorBalance) => (
                        <div
                          key={balance.asset}
                          className="flex items-center justify-between p-2 rounded-lg bg-muted/50"
                        >
                          <span className="font-medium">{balance.asset}</span>
                          <div className="text-right">
                            <div className="font-mono">{formatNumber(balance.total, 8)}</div>
                            <div className="text-xs text-muted-foreground">
                              Available: {formatNumber(balance.available, 8)}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-center text-muted-foreground py-4">No balances available</p>
                  )}
                </CardContent>
              </Card>

              {/* Update Credentials Card */}
              <Card>
                <CardHeader>
                  <CardTitle>Update Credentials</CardTitle>
                  <CardDescription>Update API credentials for {selectedConnector}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {selectedConnectorInfo?.required_credentials?.map((credKey) => (
                      <div key={credKey} className="space-y-2">
                        <Label htmlFor={`update-${credKey}`}>{formatCredentialLabel(credKey)}</Label>
                        <div className="relative">
                          <Input
                            id={`update-${credKey}`}
                            type={isSecretField(credKey) && !showCredentials ? "password" : "text"}
                            placeholder={`Enter new ${formatCredentialLabel(credKey).toLowerCase()}`}
                            value={credentials[credKey] || ""}
                            onChange={(e) =>
                              setCredentials({ ...credentials, [credKey]: e.target.value })
                            }
                          />
                          {isSecretField(credKey) && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="absolute right-0 top-0"
                              onClick={() => setShowCredentials(!showCredentials)}
                            >
                              {showCredentials ? (
                                <EyeOff className="h-4 w-4" />
                              ) : (
                                <Eye className="h-4 w-4" />
                              )}
                            </Button>
                          )}
                        </div>
                      </div>
                    ))}

                    <Button
                      onClick={handleSaveCredentials}
                      disabled={savingCredentials || Object.values(credentials).every((v) => !v)}
                      className="w-full"
                    >
                      {savingCredentials ? "Saving..." : "Update Credentials"}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </>
          ) : (
            /* No Selection */
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Plug className="h-12 w-12 text-muted-foreground mb-4" />
                <p className="text-muted-foreground">Select a connector to view details or add a new one</p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
