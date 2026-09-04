"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

const formatRUL = (hours: number) => {
  if (hours <= 0 || isNaN(hours)) return "0m";
  if (hours < 48) {
    const h = Math.floor(hours);
    const m = Math.floor((hours - h) * 60);
    const hStr = h > 0 ? `${h}h` : '';
    const mStr = m > 0 ? `${m}m` : '';
    return [hStr, mStr].filter(Boolean).join(' ') || "0m";
  } else {
    const days = Math.round(hours / 24);
    return `~${days} day${days === 1 ? '' : 's'}`;
  }
};

export default function MilSpecDigitalTwin() {
  const [data, setData] = useState<any[]>([]);
  const [vibrationData, setVibrationData] = useState<any[]>([]);
  const [rawLogs, setRawLogs] = useState<string[]>([]);

  const [faultMode, setFaultMode] = useState<"normal" | "misfire" | "cooling" | "bearing">("normal");
  const [altitude, setAltitude] = useState<number>(10000);
  const [throttle, setThrottle] = useState<number>(100);
  const [ambientTemp, setAmbientTemp] = useState<number>(25);

  const [healthIndex, setHealthIndex] = useState<number>(98);
  const [rulHours, setRulHours] = useState<number>(1420);
  const [missionTier, setMissionTier] = useState<string>("CONTINUE");
  const [kurtosis, setKurtosis] = useState<number>(2.9);
  const [alertState, setAlertState] = useState<{ title: string; desc: string } | null>(null);
  const [suggestedAction, setSuggestedAction] = useState<string | null>(null);
  const [confidenceStatus, setConfidenceStatus] = useState<string>("HIGH CONFIDENCE (In Envelope)");
  
  const [activeTab, setActiveTab] = useState<"live" | "planner">("live");
  
  const [plannerAlt, setPlannerAlt] = useState(15000);
  const [plannerDur, setPlannerDur] = useState(5);
  const [plannerThrottle, setPlannerThrottle] = useState("cruise");
  const [plannerLoading, setPlannerLoading] = useState(false);
  const [plannerResult, setPlannerResult] = useState<any>(null);
  const [plannerError, setPlannerError] = useState<string | null>(null);
  
  const [latestTelemetry, setLatestTelemetry] = useState<any>(null);
  const [copilotQuery, setCopilotQuery] = useState("");
  const [copilotResponse, setCopilotResponse] = useState<string | null>(null);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [copilotError, setCopilotError] = useState<string | null>(null);

  const [ticket, setTicket] = useState<{ id: string; component: string; action: string } | null>(null);
  const activeFaultEpisodeRef = useRef<string | null>(null);
  const lastTierRef = useRef<string>("CONTINUE");

  const handleReset = async () => {
    try {
      await fetch("http://localhost:8000/api/reset", { method: "POST" });
      setRawLogs(prev => [...prev.slice(-6), `[SYS INFO] DIGITAL TWIN SIMULATION RESET ACKNOWLEDGED.`]);
    } catch (error) {
      console.error(error);
    }
  };

  const handleAskCopilot = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!copilotQuery) return;
    
    setCopilotLoading(true);
    setCopilotError(null);
    try {
      const res = await fetch("http://localhost:8000/api/copilot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: copilotQuery,
          fault_mode: faultMode,
          context: latestTelemetry || {}
        })
      });
      if (!res.ok) throw new Error("API failed");
      const json = await res.json();
      setCopilotResponse(json.answer);
    } catch (err) {
      setCopilotError("FAILED TO REACH COPILOT. RETRY.");
    } finally {
      setCopilotLoading(false);
    }
  };

  const handleRunPlanner = async (e: React.FormEvent) => {
    e.preventDefault();
    setPlannerLoading(true);
    setPlannerError(null);
    try {
      const res = await fetch("http://localhost:8000/api/planner", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ altitude: plannerAlt, duration_hours: plannerDur, throttle_pattern: plannerThrottle })
      });
      if (!res.ok) throw new Error("API failed");
      const json = await res.json();
      setPlannerResult(json);
    } catch(err) {
      setPlannerError("FAILED TO RUN PLANNER. RETRY.");
    } finally {
      setPlannerLoading(false);
    }
  };

  useEffect(() => {
    const fetchTelemetry = async () => {
      try {
        const response = await fetch(`http://localhost:8000/api/telemetry?altitude=${altitude}&throttle=${throttle}&fault_mode=${faultMode}`);
        const result = await response.json();
        setLatestTelemetry(result);

        setHealthIndex(result.analytics.health_index);
        setRulHours(result.analytics.rul_hours);
        setMissionTier(result.analytics.mission_tier);
        setKurtosis(result.engine.vibration_kurtosis);
        setSuggestedAction(result.analytics.suggested_action || null);
        setConfidenceStatus(result.environment.confidence_status || "HIGH CONFIDENCE (In Envelope)");

        // Phase 9: Speech Synthesis on Tier Transition
        const currentTier = result.analytics.mission_tier;
        if (currentTier !== lastTierRef.current) {
          if (currentTier === "DIVERT" || currentTier === "RTB") {
            const msg = new SpeechSynthesisUtterance(`Warning. Engine health critical. Recommend ${currentTier}. ${result.analytics.anomaly_reason || ""}`);
            window.speechSynthesis.speak(msg);
          }
          lastTierRef.current = currentTier;
        }

        // Phase 9: Auto-Generated Maintenance Ticket
        if (result.analytics.rul_hours < 200) { // arbitrary threshold for demo
          if (activeFaultEpisodeRef.current !== faultMode && faultMode !== "normal") {
             setTicket({
               id: `TCK-${Math.floor(Math.random() * 10000)}`,
               component: faultMode.toUpperCase(),
               action: `Inspect and repair ${faultMode} subsystem immediately.`
             });
             activeFaultEpisodeRef.current = faultMode;
          }
        } else if (faultMode === "normal") {
          activeFaultEpisodeRef.current = null;
        }

        if (result.analytics.is_anomaly) {
          if (result.analytics.ml_anomaly_score > 0.5) {
            setAlertState({ title: "SYS WARN: ML ANOMALY DETECTED", desc: `Confidence: ${(result.analytics.ml_anomaly_score * 100).toFixed(1)}%. ${result.analytics.anomaly_reason}` });
          } else if (result.analytics.z_score > 3.0) {
            setAlertState({ title: "SYS WARN: Z-SCORE ANOMALY", desc: `EGT Variance > 3σ. Z-Score: ${result.analytics.z_score}` });
          }
        } else if (result.engine.cht[0] > 120 && faultMode === "cooling") {
          setAlertState({ title: "SYS CRIT: THERMAL LIMIT", desc: "CHT baseline exceeded across all 4 cylinders." });
        } else if (faultMode === "normal") {
          setAlertState(null);
        }

        setData((prev) => [
          ...prev.slice(-25),
          {
            time: result.timestamp,
            rpm: result.engine.rpm,
            expected_rpm: result.expected?.rpm,
            egt1: result.engine.egt[0], egt2: result.engine.egt[1],
            egt3: result.engine.egt[2], egt4: result.engine.egt[3],
            expected_egt: result.expected?.egt,
          }
        ]);

        setVibrationData([
          { order: "0.5x", amp: 0.1 + Math.random() * 0.05 },
          { order: "1x", amp: 0.8 + Math.random() * 0.1 },
          { order: "2x", amp: faultMode === "bearing" ? 2.4 + Math.random() * 0.4 : 0.3 + Math.random() * 0.1 },
          { order: "3x", amp: 0.15 + Math.random() * 0.05 },
        ]);

        // Generate raw terminal log
        const logString = `[${result.timestamp}] IN: 0x${Math.floor(Math.random() * 16777215).toString(16).toUpperCase()} | RPM: ${result.engine.rpm} EGT1: ${result.engine.egt[0]} CHT: ${Math.round(result.engine.cht[0])} HI: ${result.analytics.health_index}`;
        setRawLogs(prev => [...prev.slice(-6), logString]);

      } catch (error) {
        setRawLogs(prev => [...prev.slice(-6), `[SYS ERR] DATA LINK LOSS: CONTINUING INTERROGATION...`]);
      }
    };

    const interval = setInterval(fetchTelemetry, 1000);
    return () => clearInterval(interval);
  }, [faultMode, altitude, throttle]);

  return (
    <div className="min-h-screen bg-black text-zinc-300 p-4 font-sans selection:bg-amber-500/30">
      {/* Tactical Status Bar */}
      <div className="flex justify-between text-[10px] font-mono text-zinc-500 border-b border-zinc-800 pb-2 mb-4 uppercase tracking-widest">
        <span>Link: SECURE UHF | Latency: 14ms | Freq: 2.4GHz</span>
        <span className="text-amber-500/70">ASSET: DRDO-TAPAS-04 | ENG: AUSTRO AE330 (180HP)</span>
        <span suppressHydrationWarning>SYS TIME: {new Date().toISOString()}</span>
      </div>

      <header className="mb-4 flex justify-between items-end">
        <div>
          <h1 className="text-xl font-bold tracking-widest text-zinc-100 uppercase">MALE UAV Propulsion Digital Twin</h1>
          <div className="flex items-center gap-4 mt-1 mb-2">
            <p className="text-xs font-mono text-zinc-500">PROGNOSTICS & HEALTH MANAGEMENT (PHM) SUBSYSTEM</p>
            <Button variant="outline" onClick={handleReset} className="text-[10px] font-mono h-6 px-2 rounded-sm bg-zinc-900 border-zinc-700 hover:bg-zinc-800 hover:text-white uppercase tracking-widest text-zinc-400">
              RESET SIMULATION
            </Button>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setActiveTab("live")} className={`text-[10px] font-mono h-7 px-3 rounded-sm border-zinc-800 ${activeTab === 'live' ? 'bg-zinc-800 text-white' : 'bg-black text-zinc-500'}`}>LIVE OPS</Button>
            <Button variant="outline" onClick={() => setActiveTab("planner")} className={`text-[10px] font-mono h-7 px-3 rounded-sm border-zinc-800 ${activeTab === 'planner' ? 'bg-zinc-800 text-white' : 'bg-black text-zinc-500'}`}>MISSION PLANNER</Button>
          </div>
        </div>
        <div className="text-right flex flex-col items-end">
          <div className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest mb-1">Mission Reliability</div>
          <div className={`px-3 py-1 rounded-sm text-xs font-bold font-mono uppercase tracking-widest mb-1
            ${missionTier === 'CONTINUE' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/50' : 
              missionTier === 'DERATE' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/50' : 
              missionTier === 'DIVERT' ? 'bg-orange-500/20 text-orange-400 border border-orange-500/50' : 
              'bg-red-500/20 text-red-400 border border-red-500/50'}`}>
            STATUS: {missionTier}
          </div>
          <div className={`text-2xl font-mono font-bold ${healthIndex < 60 ? 'text-red-500' : healthIndex < 85 ? 'text-amber-400' : 'text-emerald-500'}`}>
            {healthIndex.toFixed(2)}% | RUL: {rulHours}H
          </div>
          <div className="text-[10px] font-mono text-zinc-400 mt-1 uppercase tracking-widest bg-zinc-900/50 px-2 py-1 rounded-sm border border-zinc-800">
            Est. Safe Flight Time Remaining: <span className="text-zinc-200 font-bold">{formatRUL(rulHours)}</span>
          </div>
        </div>
      </header>

      {activeTab === "live" ? (
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 mt-4">

        {/* Left Column: Command & Raw Data */}
        <div className="xl:col-span-3 space-y-4">

          <Card className="bg-zinc-950 border-zinc-800 rounded-sm">
            <CardHeader className="p-3 border-b border-zinc-900">
              <CardTitle className="text-[10px] font-mono text-zinc-400 uppercase tracking-widest">Diagnostic Injection</CardTitle>
            </CardHeader>
            <CardContent className="p-3 space-y-2">
              <Button variant="outline" onClick={() => setFaultMode("normal")} className="w-full justify-start text-xs font-mono h-8 rounded-sm bg-zinc-900 border-zinc-700 hover:bg-zinc-800 hover:text-white">
                [0] NOMINAL BASELINE
              </Button>
              <Button variant="outline" onClick={() => setFaultMode("misfire")} className="w-full justify-start text-xs font-mono h-8 rounded-sm bg-zinc-900 border-red-900/50 hover:bg-red-950 hover:text-red-400 text-zinc-400">
                [1] CYL 1 MISFIRE
              </Button>
              <Button variant="outline" onClick={() => setFaultMode("cooling")} className="w-full justify-start text-xs font-mono h-8 rounded-sm bg-zinc-900 border-red-900/50 hover:bg-red-950 hover:text-red-400 text-zinc-400">
                [2] THERMAL DEGRADATION
              </Button>
              <Button variant="outline" onClick={() => setFaultMode("bearing")} className="w-full justify-start text-xs font-mono h-8 rounded-sm bg-zinc-900 border-red-900/50 hover:bg-red-950 hover:text-red-400 text-zinc-400">
                [3] BEARING SPALLING
              </Button>
            </CardContent>
          </Card>

          <Card className="bg-zinc-950 border-zinc-800 rounded-sm">
            <CardHeader className="p-3 border-b border-zinc-900">
              <CardTitle className="text-[10px] font-mono text-zinc-400 uppercase tracking-widest">Atmospheric Env (ISA)</CardTitle>
            </CardHeader>
            <CardContent className="p-3 space-y-4 text-xs font-mono">
              <div>
                <div className="flex justify-between mb-1 text-zinc-500">
                  <span>ALTITUDE MSL (FT)</span>
                  <span className="text-zinc-300">{altitude}</span>
                </div>
                <input type="range" min="0" max="30000" step="500" value={altitude} onChange={(e) => setAltitude(Number(e.target.value))} className="w-full accent-zinc-500 bg-zinc-900 h-1 cursor-crosshair" />
              </div>
              <div>
                <div className="flex justify-between mb-1 text-zinc-500">
                  <span>THROTTLE (%)</span>
                  <span className="text-zinc-300">{throttle}</span>
                </div>
                <input type="range" min="0" max="100" step="1" value={throttle} onChange={(e) => setThrottle(Number(e.target.value))} className="w-full accent-zinc-500 bg-zinc-900 h-1 cursor-crosshair" />
              </div>
              
              <div className="mt-4 border-t border-zinc-900 pt-3">
                <div className="flex justify-between items-center">
                  <span className="text-[10px] font-mono text-zinc-500">ML MODEL CONFIDENCE</span>
                  <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded-sm ${confidenceStatus.includes('HIGH') ? 'bg-emerald-500/20 text-emerald-500' : 'bg-orange-500/20 text-orange-500'}`}>{confidenceStatus}</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Ask the Twin Copilot */}
          <Card className="bg-zinc-950 border-zinc-800 rounded-sm">
            <CardHeader className="p-3 border-b border-zinc-900">
              <CardTitle className="text-[10px] font-mono text-blue-400 uppercase tracking-widest">Ask The Twin (Copilot)</CardTitle>
            </CardHeader>
            <CardContent className="p-3">
              <form onSubmit={handleAskCopilot} className="flex gap-2 mb-2">
                <input 
                  type="text" 
                  value={copilotQuery} 
                  onChange={e => setCopilotQuery(e.target.value)} 
                  placeholder="Why recommend divert?"
                  className="flex-1 bg-zinc-900 border border-zinc-800 rounded-sm px-2 text-xs font-mono text-zinc-300 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
                />
                <Button type="submit" disabled={copilotLoading} className="h-7 px-3 text-[10px] font-mono bg-blue-900/50 text-blue-400 hover:bg-blue-900 hover:text-blue-300 rounded-sm border border-blue-900">
                  {copilotLoading ? "..." : "ASK"}
                </Button>
              </form>
              {copilotError && <div className="text-[10px] font-mono text-red-500 mb-2">{copilotError}</div>}
              {copilotResponse && (
                <div className="text-xs font-mono text-zinc-400 bg-black p-2 rounded-sm border border-zinc-800">
                  <span className="text-blue-500 text-[10px] block mb-1">TWIN:</span>
                  {copilotResponse}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Raw Data Terminal */}
          <Card className="bg-black border-zinc-800 rounded-sm">
            <CardHeader className="p-2 border-b border-zinc-900 bg-zinc-950">
              <CardTitle className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">RX DATALINK LOG</CardTitle>
            </CardHeader>
            <CardContent className="p-2 h-32 overflow-hidden flex flex-col justify-end">
              {rawLogs.map((log, i) => (
                <div key={i} className="text-[10px] font-mono text-emerald-500/70 opacity-80">{log}</div>
              ))}
            </CardContent>
          </Card>

          {alertState && (
            <Alert className="bg-red-950/20 border-red-900/50 rounded-sm p-3">
              <AlertTitle className="text-xs font-mono font-bold text-red-500 uppercase tracking-widest">{alertState.title}</AlertTitle>
              <AlertDescription className="text-[10px] font-mono text-red-400/80 mt-1">{alertState.desc}</AlertDescription>
            </Alert>
          )}

          {suggestedAction && (
            <Alert className="bg-orange-950/20 border-orange-900/50 rounded-sm p-3 mt-4">
              <AlertTitle className="text-xs font-mono font-bold text-orange-500 uppercase tracking-widest">REROUTE ADVISORY</AlertTitle>
              <AlertDescription className="text-[10px] font-mono text-orange-400/80 mt-1">{suggestedAction}</AlertDescription>
            </Alert>
          )}

          {ticket && (
            <Card className="bg-zinc-950 border-red-900/50 rounded-sm mt-4">
              <CardHeader className="p-3 border-b border-red-900/50 bg-red-950/20">
                <CardTitle className="text-[10px] font-mono text-red-500 uppercase tracking-widest flex justify-between">
                  <span>MAINTENANCE TICKET</span>
                  <span>{ticket.id}</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="p-3 text-xs font-mono">
                <div className="text-zinc-500 mb-1">COMPONENT: <span className="text-red-400">{ticket.component}</span></div>
                <div className="text-zinc-500">ACTION: <span className="text-zinc-300">{ticket.action}</span></div>
                <Button onClick={() => setTicket(null)} className="w-full mt-3 h-6 text-[10px] bg-red-950/50 text-red-500 border border-red-900/50 hover:bg-red-900 hover:text-red-300 rounded-sm">ACKNOWLEDGE & CLEAR</Button>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right Column: Telemetry */}
        <div className="xl:col-span-9 space-y-4">

          <Card className="bg-zinc-950 border-zinc-800 rounded-sm">
            <CardHeader className="p-3 border-b border-zinc-900">
              <CardTitle className="text-[10px] font-mono text-amber-500/70 uppercase tracking-widest">EGT SPECTRUM [CYL 1-4]</CardTitle>
            </CardHeader>
            <CardContent className="p-4 h-52">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data}>
                  <CartesianGrid strokeDasharray="2 4" stroke="#27272a" vertical={false} />
                  <XAxis dataKey="time" stroke="#52525b" fontSize={9} fontFamily="monospace" tickMargin={8} />
                  <YAxis domain={[750, 980]} stroke="#52525b" fontSize={9} fontFamily="monospace" width={30} />
                  <Tooltip contentStyle={{ backgroundColor: "#09090b", border: "1px solid #27272a", fontFamily: "monospace", fontSize: "10px" }} />
                  <Line type="monotone" dataKey="expected_egt" name="EXPECTED" stroke="#a1a1aa" strokeWidth={1.5} strokeDasharray="4 4" dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="egt1" name="CYL 1" stroke="#f59e0b" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="egt2" name="CYL 2" stroke="#52525b" strokeWidth={1} dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="egt3" name="CYL 3" stroke="#52525b" strokeWidth={1} dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="egt4" name="CYL 4" stroke="#52525b" strokeWidth={1} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="bg-zinc-950 border-zinc-800 rounded-sm">
              <CardHeader className="p-3 border-b border-zinc-900">
                <CardTitle className="text-[10px] font-mono text-blue-500/70 uppercase tracking-widest">SHAFT SPEED [RPM]</CardTitle>
              </CardHeader>
              <CardContent className="p-4 h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data}>
                    <CartesianGrid strokeDasharray="2 4" stroke="#27272a" vertical={false} />
                    <YAxis domain={[4000, 5200]} stroke="#52525b" fontSize={9} fontFamily="monospace" width={35} />
                    <Line type="step" dataKey="expected_rpm" name="EXPECTED" stroke="#a1a1aa" strokeWidth={1.5} strokeDasharray="4 4" dot={false} isAnimationActive={false} />
                    <Line type="step" dataKey="rpm" name="RPM" stroke="#3b82f6" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card className="bg-zinc-950 border-zinc-800 rounded-sm">
              <CardHeader className="p-3 border-b border-zinc-900 flex flex-row justify-between items-center">
                <CardTitle className="text-[10px] font-mono text-emerald-500/70 uppercase tracking-widest">VIB ORDER TRACKING [FFT]</CardTitle>
                <div className="text-[10px] font-mono text-zinc-500">KURTOSIS: <span className={kurtosis > 4 ? "text-red-500" : "text-emerald-500"}>{kurtosis}</span></div>
              </CardHeader>
              <CardContent className="p-4 h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={vibrationData}>
                    <CartesianGrid strokeDasharray="2 4" stroke="#27272a" vertical={false} />
                    <XAxis dataKey="order" stroke="#52525b" fontSize={9} fontFamily="monospace" />
                    <YAxis domain={[0, 3]} stroke="#52525b" fontSize={9} fontFamily="monospace" width={20} />
                    <Bar dataKey="amp" name="AMPLITUDE" fill={faultMode === "bearing" ? "#ef4444" : "#10b981"} radius={0} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
      ) : (
        <div className="mt-4 max-w-2xl">
          <Card className="bg-zinc-950 border-zinc-800 rounded-sm">
            <CardHeader className="p-3 border-b border-zinc-900">
              <CardTitle className="text-xs font-mono text-zinc-400 uppercase tracking-widest">PRE-MISSION &quot;WHAT-IF&quot; PLANNER</CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-4 font-mono">
              <p className="text-xs text-zinc-500 mb-4">Run the digital twin&apos;s degradation model forward to simulate the health impact of a proposed mission profile.</p>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[10px] text-zinc-500 mb-1 block">TARGET ALTITUDE (FT)</label>
                  <input type="number" value={plannerAlt} onChange={e => setPlannerAlt(Number(e.target.value))} className="w-full bg-zinc-900 border border-zinc-800 p-2 text-xs text-zinc-300 rounded-sm focus:outline-none" />
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500 mb-1 block">EXPECTED DURATION (HRS)</label>
                  <input type="number" value={plannerDur} onChange={e => setPlannerDur(Number(e.target.value))} className="w-full bg-zinc-900 border border-zinc-800 p-2 text-xs text-zinc-300 rounded-sm focus:outline-none" />
                </div>
              </div>
              
              <div>
                <label className="text-[10px] text-zinc-500 mb-1 block">THROTTLE PATTERN</label>
                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => setPlannerThrottle("cruise")} className={`flex-1 h-8 text-[10px] rounded-sm border-zinc-800 ${plannerThrottle === 'cruise' ? 'bg-zinc-800 text-white' : 'bg-zinc-900 text-zinc-500'}`}>CRUISE (NORMAL)</Button>
                  <Button variant="outline" onClick={() => setPlannerThrottle("aggressive")} className={`flex-1 h-8 text-[10px] rounded-sm border-zinc-800 ${plannerThrottle === 'aggressive' ? 'bg-zinc-800 text-white' : 'bg-zinc-900 text-zinc-500'}`}>AGGRESSIVE (HIGH LOAD)</Button>
                </div>
              </div>

              <Button onClick={handleRunPlanner} disabled={plannerLoading} className="w-full h-8 text-xs bg-zinc-800 text-white rounded-sm hover:bg-zinc-700">
                {plannerLoading ? "SIMULATING..." : "RUN SIMULATION"}
              </Button>
              
              {plannerError && <div className="text-xs text-red-500 mt-2">{plannerError}</div>}
              
              {plannerResult && (
                <div className={`mt-4 p-4 rounded-sm border ${plannerResult.is_safe ? 'bg-emerald-950/20 border-emerald-900/50' : 'bg-red-950/20 border-red-900/50'}`}>
                  <div className={`text-sm font-bold mb-2 ${plannerResult.is_safe ? 'text-emerald-500' : 'text-red-500'}`}>
                    {plannerResult.is_safe ? 'MISSION PROFILE: SAFE' : 'MISSION PROFILE: UNSAFE'}
                  </div>
                  <div className="text-xs text-zinc-400 mb-2">{plannerResult.message}</div>
                  <div className="flex justify-between text-[10px] text-zinc-500">
                    <span>EST FINAL HEALTH: <span className="text-zinc-300">{plannerResult.final_health_index}%</span></span>
                    <span>EST REMAINING RUL: <span className="text-zinc-300">{plannerResult.final_rul_hours}H</span></span>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}