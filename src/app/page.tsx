"use client";

import React, { useState, useEffect, useRef } from "react";
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Activity, ShieldAlert, Cpu, LayoutDashboard, BookOpen, Settings2, Moon, Sun, RotateCw, MessageSquare, ClipboardList } from "lucide-react";

type FaultMode = "normal" | "misfire" | "cooling" | "bearing";

const FAULT_OPTIONS: { value: FaultMode; label: string; desc: string }[] = [
  { value: "normal",  label: "Nominal Baseline",        desc: "Nominal Baseline — clear all fault injections" },
  { value: "misfire", label: "Cyl 1 Misfire Injection", desc: "Inject an isolated misfire on Cylinder 1" },
  { value: "cooling", label: "Thermal Degradation",     desc: "Simulate a cooling-loop failure (CHT rise)" },
  { value: "bearing", label: "Bearing Micro-Spalling",  desc: "Simulate bearing wear (kurtosis rise)" },
];
type TelemetrySample = {
  time: string;
  egt1: number; egt2: number; egt3: number; egt4: number;
  cht1: number; cht2: number; cht3: number; cht4: number;
  rpm: number; map: number; op: number; ff: number; hi: number; rul: number;
};
type FftBin = { order: string; amp: number };

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function HighDensityDigitalTwin() {
  const [activeTab, setActiveTab] = useState<"dashboard" | "planner" | "docs" | "settings">("dashboard");
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  const [data, setData] = useState<TelemetrySample[]>([]);
  const [vibrationData, setVibrationData] = useState<FftBin[]>([]);
  const [rawLogs, setRawLogs] = useState<string[]>([]);

  const [faultMode, setFaultMode] = useState<FaultMode>("normal");
  const [altitude, setAltitude] = useState<number>(10000);
  const [pollingRate, setPollingRate] = useState<number>(1000);

  const [metrics, setMetrics] = useState({
    healthIndex: 98, rulHours: 1420, kurtosis: 2.9,
    rpm: 4785, map: 29.9, op: 60.0, ff: 8.5
  });

  const [alertState, setAlertState] = useState<{ title: string; desc: string } | null>(null);
  const [sysTime, setSysTime] = useState<string>("SYNCING_CLOCK...");

  const [latestTelemetry, setLatestTelemetry] = useState<any>(null);
  const [copilotQuery, setCopilotQuery] = useState("");
  const [copilotResponse, setCopilotResponse] = useState<string | null>(null);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [copilotError, setCopilotError] = useState<string | null>(null);

  const [plannerAlt, setPlannerAlt] = useState(15000);
  const [plannerDur, setPlannerDur] = useState(5);
  const [plannerThrottle, setPlannerThrottle] = useState("cruise");
  const [plannerLoading, setPlannerLoading] = useState(false);
  const [plannerResult, setPlannerResult] = useState<any>(null);
  const [plannerError, setPlannerError] = useState<string | null>(null);

  const [ticket, setTicket] = useState<{ id: string; component: string; action: string } | null>(null);
  const activeFaultEpisodeRef = useRef<string | null>(null);

  const handleReset = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/reset`, { method: "POST" });
      if (!res.ok) throw new Error("reset failed");
      window.location.reload();
    } catch {
      setRawLogs(prev => [...prev.slice(-28), `[SYS ERR] RESET FAILED — DATALINK DISCONNECT...`]);
    }
  };

  const handleAskCopilot = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!copilotQuery) return;

    setCopilotLoading(true);
    setCopilotError(null);
    try {
      const res = await fetch(`${API_BASE}/api/copilot`, {
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
    } catch {
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
      const res = await fetch(`${API_BASE}/api/planner`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ altitude: plannerAlt, duration_hours: plannerDur, throttle_pattern: plannerThrottle })
      });
      if (!res.ok) throw new Error("API failed");
      const json = await res.json();
      setPlannerResult(json);
    } catch {
      setPlannerError("FAILED TO RUN PLANNER. RETRY.");
    } finally {
      setPlannerLoading(false);
    }
  };

  const [logWidth, setLogWidth] = useState(0);
  const logBodyRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = logBodyRef.current;
    if (!el) return;
    const update = () => setLogWidth(el.clientWidth);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const longestLine = Math.max(35, ...rawLogs.map((l) => l.length));
  const logFont = Math.max(7, Math.min(10, Math.floor(logWidth / (longestLine * 0.62))));

  useEffect(() => {
    const fetchTelemetry = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/telemetry?altitude=${altitude}&fault_mode=${faultMode}`);
        const result = await response.json();
        setLatestTelemetry(result);

        setMetrics({
          healthIndex: result.analytics.health_index,
          rulHours: result.analytics.rul_hours,
          kurtosis: result.engine.vibration_kurtosis,
          rpm: result.engine.rpm,
          map: result.engine.map,
          op: result.engine.op,
          ff: result.engine.ff
        });

        setAlertState(result.analytics.alert);
        setVibrationData(result.vibration_fft);
        setSysTime(new Date().toISOString().replace('T', ' ').substring(0, 19) + 'Z');

        if (result.analytics.rul_hours < 200) {
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

        setData((prev) => [
          ...prev.slice(-30),
          {
            time: result.timestamp,
            egt1: result.engine.egt[0], egt2: result.engine.egt[1], egt3: result.engine.egt[2], egt4: result.engine.egt[3],
            cht1: result.engine.cht[0], cht2: result.engine.cht[1], cht3: result.engine.cht[2], cht4: result.engine.cht[3],
            rpm: result.engine.rpm, map: result.engine.map, op: result.engine.op, ff: result.engine.ff,
            hi: result.analytics.health_index, rul: result.analytics.rul_hours,
          }
        ]);

        const logString = `[${result.timestamp}] ${result.hex_id.replace('0x', '')} RPM:${result.engine.rpm} MAP:${result.engine.map} OP:${result.engine.op} HI:${result.analytics.health_index}`;
        setRawLogs(prev => [...prev.slice(-28), logString]);

      } catch {
        setRawLogs(prev => [...prev.slice(-28), `[SYS ERR] DATALINK DISCONNECT...`]);
      }
    };

    const interval = setInterval(fetchTelemetry, pollingRate);
    return () => clearInterval(interval);
  }, [faultMode, altitude, pollingRate]);

  const panelCls = "bg-white dark:bg-[#121214] shadow-sm";

  const statusColor =
    metrics.healthIndex > 85 ? "text-emerald-600 dark:text-emerald-400"
    : metrics.healthIndex > 60 ? "text-amber-500 dark:text-amber-400"
    : "text-red-600 dark:text-red-400";
  const statusLabel =
    metrics.healthIndex > 85 ? "NOMINAL"
    : metrics.healthIndex > 60 ? "CAUTION"
    : "CRITICAL";
  const gridColor = theme === "dark" ? "#27272a" : "#e4e4e7";
  const axisColor = theme === "dark" ? "#52525b" : "#a1a1aa";

  const latest = data[data.length - 1];
  const egtAvg = latest ? Math.round((latest.egt1 + latest.egt2 + latest.egt3 + latest.egt4) / 4) : null;
  const chtAvg = latest ? Math.round((latest.cht1 + latest.cht2 + latest.cht3 + latest.cht4) / 4) : null;

  const kpis = [
    { key: 'hi',  label: 'Health (HI)',     value: String(metrics.healthIndex), unit: '%',    cls: statusColor,                          color: '#10b981' },
    { key: 'rpm', label: 'RPM',             value: String(metrics.rpm),          unit: '',      cls: 'text-blue-600 dark:text-blue-400',   color: '#3b82f6' },
    { key: 'map', label: 'Manifold (MAP)',  value: String(metrics.map),          unit: 'inHg',  cls: 'text-zinc-800 dark:text-zinc-100',  color: '#8b8f98' },
    { key: 'op',  label: 'Oil Press',       value: String(metrics.op),           unit: 'psi',   cls: 'text-amber-600 dark:text-amber-500', color: '#f59e0b' },
    { key: 'ff',  label: 'Fuel Flow',       value: String(metrics.ff),           unit: 'GPH',   cls: 'text-zinc-800 dark:text-zinc-100',  color: '#8b8f98' },
    { key: 'rul', label: 'Est RUL',         value: String(metrics.rulHours),     unit: 'H',     cls: 'text-zinc-800 dark:text-zinc-100',  color: '#8b8f98' },
  ] as const;

  return (
    <div className={`h-screen w-screen overflow-hidden font-sans flex transition-colors duration-200 ${theme === "dark" ? "dark bg-[#050505] text-zinc-100" : "bg-zinc-100 text-zinc-900"}`}>

      <div className="w-16 border-r border-zinc-200 dark:border-white/5 bg-white dark:bg-[#0a0a0a] flex flex-col items-center py-6 space-y-8 z-10 shrink-0 shadow-sm">
        <div className="text-blue-600 dark:text-blue-500 font-bold text-xl mb-4 tracking-tighter">DT</div>
        <button onClick={() => setActiveTab("dashboard")} className={`p-3 rounded-xl transition-colors ${activeTab === "dashboard" ? "bg-blue-100 text-blue-600 dark:bg-blue-600/20 dark:text-blue-400" : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"}`} title="Dashboard">
          <LayoutDashboard className="w-5 h-5" />
        </button>
        <button onClick={() => setActiveTab("planner")} className={`p-3 rounded-xl transition-colors ${activeTab === "planner" ? "bg-blue-100 text-blue-600 dark:bg-blue-600/20 dark:text-blue-400" : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"}`} title="Mission Planner">
          <ClipboardList className="w-5 h-5" />
        </button>
        <button onClick={() => setActiveTab("docs")} className={`p-3 rounded-xl transition-colors ${activeTab === "docs" ? "bg-blue-100 text-blue-600 dark:bg-blue-600/20 dark:text-blue-400" : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"}`} title="Documentation">
          <BookOpen className="w-5 h-5" />
        </button>
        <button onClick={() => setActiveTab("settings")} className={`p-3 rounded-xl transition-colors mt-auto ${activeTab === "settings" ? "bg-blue-100 text-blue-600 dark:bg-blue-600/20 dark:text-blue-400" : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"}`} title="Settings">
          <Settings2 className="w-5 h-5" />
        </button>
      </div>

      <div className="flex-1 flex flex-col p-4 md:p-6 overflow-x-hidden overflow-y-auto xl:overflow-hidden">

        <div className="flex justify-between items-center text-[10px] font-mono text-zinc-500 dark:text-zinc-400 border-b border-zinc-200 dark:border-white/10 pb-3 mb-4 tracking-widest uppercase shrink-0">
          <div className="flex space-x-6">
            <span>ASSET: <span className="text-zinc-900 dark:text-zinc-100 font-semibold">DRDO-TAPAS-04</span></span>
            <span>STATUS: <span className={`font-semibold ${statusColor}`}>{statusLabel} [HI: {metrics.healthIndex}%]</span></span>
            <span>LINK: <span className="text-emerald-600 dark:text-emerald-400 font-semibold">SECURE UHF</span></span>
          </div>
          <span>SYSTEM TIME: <span className="text-zinc-900 dark:text-zinc-100 font-semibold">{sysTime}</span></span>
        </div>

        {activeTab === "dashboard" && (
          <div className="flex-1 grid grid-cols-1 xl:grid-cols-12 gap-4 min-h-0">

            <div className="xl:col-span-9 flex flex-col gap-4 min-w-0 xl:min-h-0">

              <div className="grid grid-cols-2 sm:grid-cols-3 2xl:grid-cols-6 gap-3 shrink-0">
                {kpis.map((k) => (
                  <Card key={k.key} className={cn(panelCls, "flex flex-col justify-center min-w-0")}>
                    <CardContent className="p-3 flex flex-col flex-1 min-h-0">
                      <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1 truncate">{k.label}</p>
                      <p className={`text-2xl font-semibold tracking-tight leading-tight ${k.cls}`}>
                        {k.value}
                        {k.unit && <span className="text-[11px] font-semibold text-zinc-500 dark:text-zinc-400 ml-1">{k.unit}</span>}
                      </p>
                      <div className="mt-2 h-10 min-w-0 shrink-0">
                        {data.length > 1 && (
                          <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
                              <defs>
                                <linearGradient id={`spark-${k.key}`} x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="0%" stopColor={k.color} stopOpacity={0.22} />
                                  <stop offset="100%" stopColor={k.color} stopOpacity={0} />
                                </linearGradient>
                              </defs>
                              <XAxis dataKey="time" hide />
                              <YAxis domain={['dataMin - 1', 'dataMax + 1']} hide />
                              <Area type="monotone" dataKey={k.key} stroke={k.color} strokeWidth={1.5} fill={`url(#spark-${k.key})`} isAnimationActive={false} />
                            </AreaChart>
                          </ResponsiveContainer>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 h-[280px] sm:h-[340px] xl:h-auto xl:flex-[3] min-h-0">
                <Card className={cn(panelCls, "flex flex-col min-h-0")}>
                  <CardHeader className="p-3 pb-0 shrink-0 border-b border-zinc-100 dark:border-white/5 flex flex-wrap items-center gap-x-2 gap-y-1">
                    <CardTitle className="text-xs font-bold text-zinc-600 dark:text-zinc-400 uppercase tracking-widest">EGT Real-Time</CardTitle>
                    <span className="flex items-baseline gap-1 px-2 py-0.5 rounded-md bg-zinc-100 dark:bg-white/5 whitespace-nowrap">
                      <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-400 dark:text-zinc-500">Avg</span>
                      <span className="text-sm font-bold font-mono tabular-nums text-zinc-800 dark:text-zinc-100">{egtAvg ?? '--'}°C</span>
                    </span>
                  </CardHeader>
                  <CardContent className="flex-1 p-3 min-h-0">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={data}>
                        <CartesianGrid strokeDasharray="2 4" stroke={gridColor} vertical={false} />
                        <XAxis dataKey="time" hide />
                        <YAxis domain={['dataMin - 5', 'dataMax + 5']} stroke={axisColor} fontSize={9} width={30} tickFormatter={(v) => `${Math.round(v)}°`} />
                        <Tooltip contentStyle={{ backgroundColor: theme === 'dark' ? "#09090b" : "#ffffff", border: `1px solid ${gridColor}`, fontSize: "11px", borderRadius: "6px", color: theme === 'dark' ? "#f4f4f5" : "#18181b" }} />
                        <Area type="monotone" name="CYL 1" dataKey="egt1" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.06} strokeWidth={2} isAnimationActive={false} />
                        <Area type="monotone" name="CYL 2" dataKey="egt2" stroke="#3b82f6" fill="transparent" strokeWidth={1} isAnimationActive={false} />
                        <Area type="monotone" name="CYL 3" dataKey="egt3" stroke="#ef4444" fill="transparent" strokeWidth={1} isAnimationActive={false} />
                        <Area type="monotone" name="CYL 4" dataKey="egt4" stroke="#a855f7" fill="transparent" strokeWidth={1} isAnimationActive={false} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                <Card className={cn(panelCls, "flex flex-col min-h-0")}>
                  <CardHeader className="p-3 pb-0 shrink-0 border-b border-zinc-100 dark:border-white/5 flex flex-wrap items-center gap-x-2 gap-y-1">
                    <CardTitle className="text-xs font-bold text-zinc-600 dark:text-zinc-400 uppercase tracking-widest">CHT Real-Time</CardTitle>
                    <span className="flex items-baseline gap-1 px-2 py-0.5 rounded-md bg-zinc-100 dark:bg-white/5 whitespace-nowrap">
                      <span className="text-[9px] font-mono uppercase tracking-wider text-zinc-400 dark:text-zinc-500">Avg</span>
                      <span className="text-sm font-bold font-mono tabular-nums text-zinc-800 dark:text-zinc-100">{chtAvg ?? '--'}°C</span>
                    </span>
                  </CardHeader>
                  <CardContent className="flex-1 p-3 min-h-0">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={data}>
                        <CartesianGrid strokeDasharray="2 4" stroke={gridColor} vertical={false} />
                        <XAxis dataKey="time" hide />
                        <YAxis domain={['dataMin - 1', 'dataMax + 1']} stroke={axisColor} fontSize={9} width={30} tickFormatter={(v) => `${Math.round(v)}°`} />
                        <Tooltip contentStyle={{ backgroundColor: theme === 'dark' ? "#09090b" : "#ffffff", border: `1px solid ${gridColor}`, fontSize: "11px", borderRadius: "6px", color: theme === 'dark' ? "#f4f4f5" : "#18181b" }} />
                        <Area type="monotone" name="CYL 1" dataKey="cht1" stroke="#10b981" fill="#10b981" fillOpacity={0.06} strokeWidth={2} isAnimationActive={false} />
                        <Area type="monotone" name="CYL 2" dataKey="cht2" stroke="#8b5cf6" fill="transparent" strokeWidth={1} isAnimationActive={false} />
                        <Area type="monotone" name="CYL 3" dataKey="cht3" stroke="#f59e0b" fill="transparent" strokeWidth={1} isAnimationActive={false} />
                        <Area type="monotone" name="CYL 4" dataKey="cht4" stroke="#0ea5e9" fill="transparent" strokeWidth={1} isAnimationActive={false} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 h-[190px] sm:h-[220px] xl:h-auto xl:flex-[2] min-h-0">
                <Card className={cn(panelCls, "col-span-3 flex flex-col min-h-0")}>
                  <CardHeader className="p-3 pb-0 shrink-0 border-b border-zinc-100 dark:border-white/5">
                    <CardTitle className="text-xs font-bold text-zinc-600 dark:text-zinc-400 uppercase tracking-widest">Vibration Order Tracking [FFT]</CardTitle>
                  </CardHeader>
                  <CardContent className="p-3 flex-1 min-h-0">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={vibrationData}>
                        <CartesianGrid strokeDasharray="2 4" stroke={gridColor} vertical={false} />
                        <XAxis dataKey="order" stroke={axisColor} fontSize={10} tickMargin={5} />
                        <YAxis domain={[0, 3]} stroke={axisColor} fontSize={9} width={20} />
                        <Tooltip cursor={{ fill: gridColor, opacity: 0.5 }} contentStyle={{ backgroundColor: theme === 'dark' ? "#09090b" : "#ffffff", border: `1px solid ${gridColor}`, fontSize: "11px", borderRadius: "6px", color: theme === 'dark' ? "#f4f4f5" : "#18181b" }} />
                        <Bar name="Amplitude" dataKey="amp" fill={faultMode === "bearing" ? "#ef4444" : "#0ea5e9"} radius={[2, 2, 0, 0]} isAnimationActive={false} />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
                <Card className={cn(panelCls, "flex flex-col justify-center items-center text-center p-4")}>
                  <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">Kurtosis Index</p>
                  <p className={`text-5xl font-light tracking-tight mb-2 ${metrics.kurtosis > 4.5 ? "text-red-600 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400"}`}>{metrics.kurtosis}</p>
                  <p className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">{metrics.kurtosis > 4.5 ? "WEAR DETECTED" : "BASELINE NOMINAL"}</p>
                </Card>
              </div>

            </div>

            <div className="xl:col-span-3 grid grid-cols-1 xl:flex xl:flex-col gap-4 min-w-0 xl:min-h-0">

              <Card className={cn(panelCls, "shrink-0")}>
                <CardHeader className="p-4 border-b border-zinc-100 dark:border-white/5">
                  <CardTitle className="text-xs font-bold text-zinc-800 dark:text-zinc-200 flex items-center">
                    <Cpu className="w-4 h-4 mr-2 text-blue-600 dark:text-blue-500" /> Ground Command
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-4 space-y-6">

                  <div className="space-y-3">
                    <div className="flex justify-between text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                      <span>Altitude MSL</span><span className="text-zinc-800 dark:text-zinc-100">{altitude} ft</span>
                    </div>
                    <input type="range" min="0" max="30000" step="500" value={altitude} onChange={(e) => setAltitude(Number(e.target.value))} className="w-full accent-blue-600 dark:accent-blue-500 bg-zinc-200 dark:bg-zinc-800 h-1 rounded-full appearance-none cursor-pointer" />
                  </div>

                  <div className="space-y-3 pt-4 border-t border-zinc-100 dark:border-white/5">
                    <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">Diagnostic Injection</p>
                    <div className="flex flex-col gap-1.5">
                      {FAULT_OPTIONS.map((opt) => {
                        const active = faultMode === opt.value;
                        return (
                          <button
                            key={opt.value}
                            type="button"
                            aria-pressed={active}
                            onClick={() => setFaultMode(opt.value)}
                            title={opt.desc}
                            className={cn(
                              "w-full text-left px-3.5 py-2.5 rounded-lg border text-xs font-semibold tracking-wide transition-colors",
                              active
                                ? "bg-blue-600 border-blue-600 text-white shadow-sm"
                                : "bg-zinc-50 dark:bg-[#1a1a1c] border-zinc-200 dark:border-white/10 text-zinc-700 dark:text-zinc-300 hover:border-blue-400 dark:hover:border-blue-500/60"
                            )}
                          >
                            <span className="block truncate">{opt.label}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="pt-3 border-t border-zinc-100 dark:border-white/5 space-y-2">
                    <button
                      type="button"
                      onClick={handleReset}
                      className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg border text-[11px] font-semibold uppercase tracking-wider transition-colors border-zinc-300 text-zinc-600 hover:border-emerald-500 hover:text-emerald-600 dark:border-white/10 dark:text-zinc-300 dark:hover:border-emerald-400/70 dark:hover:text-emerald-400"
                    >
                      <RotateCw className="w-3.5 h-3.5" /> Restart Simulation
                    </button>
                  </div>
                </CardContent>
              </Card>

              <Card className={cn(panelCls, "shrink-0")}>
                <CardHeader className="p-4 border-b border-zinc-100 dark:border-white/5">
                  <CardTitle className="text-xs font-bold text-zinc-800 dark:text-zinc-200 flex items-center">
                    <MessageSquare className="w-4 h-4 mr-2 text-blue-600 dark:text-blue-500" /> Ask The Twin (Copilot)
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-4">
                  <form onSubmit={handleAskCopilot} className="flex gap-2 mb-2">
                    <input
                      type="text"
                      value={copilotQuery}
                      onChange={e => setCopilotQuery(e.target.value)}
                      placeholder="Why recommend divert?"
                      className="flex-1 bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-md px-2 text-xs text-zinc-700 dark:text-zinc-300 placeholder:text-zinc-400 dark:placeholder:text-zinc-600 focus:outline-none focus:border-blue-500"
                    />
                    <Button type="submit" disabled={copilotLoading} className="h-8 px-3 text-[10px] font-semibold bg-blue-600 text-white hover:bg-blue-700 rounded-md">
                      {copilotLoading ? "..." : "ASK"}
                    </Button>
                  </form>
                  {copilotError && <div className="text-[10px] text-red-500 mb-2">{copilotError}</div>}
                  {copilotResponse && (
                    <div className="text-xs text-zinc-600 dark:text-zinc-400 bg-zinc-50 dark:bg-black/30 p-2 rounded-md border border-zinc-100 dark:border-white/5">
                      <span className="text-blue-600 dark:text-blue-400 text-[10px] block mb-1 font-semibold">TWIN:</span>
                      {copilotResponse}
                    </div>
                  )}
                </CardContent>
              </Card>

              {alertState && (
                <Alert className="bg-red-50 dark:bg-red-950/40 border-red-200 dark:border-red-900/50 rounded-xl shrink-0 shadow-sm">
                  <ShieldAlert className="h-5 w-5 text-red-600 dark:text-red-400" />
                  <AlertTitle className="text-xs font-bold text-red-700 dark:text-red-400 uppercase tracking-widest">{alertState.title}</AlertTitle>
                  <AlertDescription className="text-[11px] font-medium text-red-600 dark:text-red-300/80 mt-1 leading-relaxed">{alertState.desc}</AlertDescription>
                </Alert>
              )}

              {ticket && (
                <Card className="bg-white dark:bg-[#121214] border-red-300 dark:border-red-900/50 rounded-xl shrink-0 shadow-sm">
                  <CardHeader className="p-3 border-b border-red-100 dark:border-red-900/50 bg-red-50 dark:bg-red-950/20">
                    <CardTitle className="text-[10px] font-bold text-red-600 dark:text-red-400 uppercase tracking-widest flex justify-between">
                      <span>MAINTENANCE TICKET</span>
                      <span>{ticket.id}</span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-3 text-xs">
                    <div className="text-zinc-500 mb-1">COMPONENT: <span className="text-red-500 font-semibold">{ticket.component}</span></div>
                    <div className="text-zinc-500">ACTION: <span className="text-zinc-700 dark:text-zinc-300">{ticket.action}</span></div>
                    <Button onClick={() => setTicket(null)} className="w-full mt-3 h-7 text-[10px] bg-red-50 dark:bg-red-950/50 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-900/50 hover:bg-red-100 dark:hover:bg-red-900 rounded-md">ACKNOWLEDGE &amp; CLEAR</Button>
                  </CardContent>
                </Card>
              )}

              <Card className="bg-zinc-900 dark:bg-[#1c1c1f] dark:ring-white/10 h-[220px] sm:h-[240px] xl:h-auto xl:flex-1 xl:min-h-0 flex flex-col min-w-0 overflow-hidden shadow-inner">
                <CardHeader className="p-3 border-b border-zinc-700/60 dark:border-white/10 bg-black/40 dark:bg-black/60 shrink-0">
                  <CardTitle className="text-[10px] font-mono font-bold text-zinc-300 dark:text-zinc-200 uppercase flex items-center tracking-widest">
                    <Activity className="w-3 h-3 mr-2 animate-pulse text-emerald-400" /> Datalink Hex Log
                  </CardTitle>
                </CardHeader>
                <CardContent ref={logBodyRef} className="px-3 py-2 flex-1 flex flex-col justify-end overflow-hidden">
                  {rawLogs.length === 0 && (
                    <div className="font-mono text-emerald-400/40" style={{ fontSize: 10, lineHeight: 1.5 }}>[SYS] AWAITING DATALINK FRAME...</div>
                  )}
                  {rawLogs.map((log, i) => (
                    <div key={i} className="font-mono text-emerald-400/90 whitespace-nowrap" style={{ fontSize: logFont, lineHeight: 1.5 }}>{log}</div>
                  ))}
                </CardContent>
              </Card>

            </div>
          </div>
        )}

        {activeTab === "planner" && (
          <div className="flex-1 overflow-y-auto pr-2 pb-10">
            <Card className={cn(panelCls, "p-6 max-w-2xl mx-auto mt-4 shadow-lg")}>
              <CardTitle className="text-sm font-bold text-zinc-800 dark:text-zinc-200 uppercase tracking-widest mb-1">Pre-Mission &quot;What-If&quot; Planner</CardTitle>
              <p className="text-xs text-zinc-500 mb-6">Run the digital twin&apos;s degradation model forward to simulate the health impact of a proposed mission profile.</p>

              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <label className="text-[10px] text-zinc-500 mb-1 block uppercase tracking-wider">Target Altitude (ft)</label>
                  <input type="number" value={plannerAlt} onChange={e => setPlannerAlt(Number(e.target.value))} className="w-full bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 p-2 text-xs text-zinc-700 dark:text-zinc-300 rounded-md focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500 mb-1 block uppercase tracking-wider">Expected Duration (hrs)</label>
                  <input type="number" value={plannerDur} onChange={e => setPlannerDur(Number(e.target.value))} className="w-full bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 p-2 text-xs text-zinc-700 dark:text-zinc-300 rounded-md focus:outline-none focus:border-blue-500" />
                </div>
              </div>

              <div className="mb-6">
                <label className="text-[10px] text-zinc-500 mb-1 block uppercase tracking-wider">Throttle Pattern</label>
                <div className="flex gap-2">
                  <button onClick={() => setPlannerThrottle("cruise")} className={`flex-1 h-9 text-[11px] font-semibold rounded-md border transition-colors ${plannerThrottle === 'cruise' ? 'bg-blue-600 border-blue-600 text-white' : 'bg-zinc-50 dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800 text-zinc-500'}`}>CRUISE (NORMAL)</button>
                  <button onClick={() => setPlannerThrottle("aggressive")} className={`flex-1 h-9 text-[11px] font-semibold rounded-md border transition-colors ${plannerThrottle === 'aggressive' ? 'bg-blue-600 border-blue-600 text-white' : 'bg-zinc-50 dark:bg-zinc-900 border-zinc-200 dark:border-zinc-800 text-zinc-500'}`}>AGGRESSIVE (HIGH LOAD)</button>
                </div>
              </div>

              <Button onClick={handleRunPlanner} disabled={plannerLoading} className="w-full h-9 text-xs font-semibold bg-blue-600 text-white rounded-md hover:bg-blue-700">
                {plannerLoading ? "SIMULATING..." : "RUN SIMULATION"}
              </Button>

              {plannerError && <div className="text-xs text-red-500 mt-2">{plannerError}</div>}

              {plannerResult && (
                <div className={`mt-4 p-4 rounded-lg border ${plannerResult.is_safe ? 'bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-900/50' : 'bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-900/50'}`}>
                  <div className={`text-sm font-bold mb-2 ${plannerResult.is_safe ? 'text-emerald-600 dark:text-emerald-500' : 'text-red-600 dark:text-red-500'}`}>
                    {plannerResult.is_safe ? 'MISSION PROFILE: SAFE' : 'MISSION PROFILE: UNSAFE'}
                  </div>
                  <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-2">{plannerResult.message}</div>
                  <div className="flex justify-between text-[10px] text-zinc-500">
                    <span>EST FINAL HEALTH: <span className="text-zinc-700 dark:text-zinc-300 font-semibold">{plannerResult.final_health_index}%</span></span>
                    <span>EST REMAINING RUL: <span className="text-zinc-700 dark:text-zinc-300 font-semibold">{plannerResult.final_rul_hours}H</span></span>
                  </div>
                </div>
              )}
            </Card>
          </div>
        )}

        {activeTab === "docs" && (
          <div className="flex-1 overflow-y-auto pr-2 pb-10">
            <Card className={cn(panelCls, "p-8 max-w-4xl mx-auto mt-4 shadow-lg")}>
              <h2 className="text-2xl font-bold mb-2 text-zinc-900 dark:text-zinc-100 tracking-tight">System Architecture &amp; Diagnostics</h2>
              <p className="text-sm text-zinc-500 mb-8 border-b border-zinc-100 dark:border-white/5 pb-4">Version 2.4.0 • Reference Manual for Ground Control Station (GCS) Operators</p>

              <div className="space-y-10 text-sm text-zinc-600 dark:text-zinc-400 leading-relaxed">
                <section>
                  <h3 className="text-zinc-900 dark:text-white font-semibold text-lg mb-3 flex items-center">
                    <div className="w-2 h-2 bg-amber-500 rounded-full mr-3"></div> Exhaust Gas Temperature (EGT)
                  </h3>
                  <p className="mb-3">EGT is the primary indicator of combustion health. The digital twin utilizes an auto-zooming real-time chart to monitor subtle shifts in thermal equilibrium. A rapid spike in a single cylinder indicates an isolated misfire or injector fault, causing unburned fuel to ignite in the exhaust manifold.</p>
                  <div className="bg-zinc-50 dark:bg-black/30 p-4 rounded-lg border border-zinc-100 dark:border-white/5">
                    <strong className="text-zinc-800 dark:text-zinc-300">Action Protocol:</strong> If a cylinder-isolation anomaly exceeds threshold on a single cylinder, initiate immediate fuel-injector diagnostic routine and prepare to derate throttle.
                  </div>
                </section>

                <section>
                  <h3 className="text-zinc-900 dark:text-white font-semibold text-lg mb-3 flex items-center">
                    <div className="w-2 h-2 bg-emerald-500 rounded-full mr-3"></div> Cylinder Head Temperature (CHT)
                  </h3>
                  <p className="mb-3">Monitors the structural thermal load of the engine block. A uniform rise across all cylinders (visible as synchronized thermal climbing in the CHT chart) indicates a failure in the liquid cooling loop, requiring immediate action to prevent catastrophic engine seizure.</p>
                  <div className="bg-zinc-50 dark:bg-black/30 p-4 rounded-lg border border-zinc-100 dark:border-white/5">
                    <strong className="text-zinc-800 dark:text-zinc-300">Action Protocol:</strong> If CHT exceeds 120°C concurrently across Cyl 1-4, immediately open radiator cowlings (if applicable) and reduce shaft speed to 3000 RPM.
                  </div>
                </section>

                <section>
                  <h3 className="text-zinc-900 dark:text-white font-semibold text-lg mb-3 flex items-center">
                    <div className="w-2 h-2 bg-blue-500 rounded-full mr-3"></div> Physics &amp; Mathematical Models
                  </h3>
                  <p>The backend Python server generates anticipated baselines using the International Standard Atmosphere (ISA) model and a 4-stroke Otto cycle simulation. It calculates the expected Manifold Absolute Pressure (MAP) and baseline RPM by applying altitude lapse rates to sea-level metrics. Any deviation between the physical sensor data and this mathematical model indicates mechanical degradation (Remaining Useful Life reduction).</p>
                </section>

                <section>
                  <h3 className="text-zinc-900 dark:text-white font-semibold text-lg mb-3 flex items-center">
                    <div className="w-2 h-2 bg-cyan-500 rounded-full mr-3"></div> Fast Fourier Transform (FFT) &amp; Kurtosis
                  </h3>
                  <p className="mb-3">High-frequency vibration data is processed via FFT to isolate specific mechanical orders. Kurtosis provides a statistical measure of the "tailedness" of this vibration distribution. A healthy engine produces a baseline Gaussian distribution of ~3.0.</p>
                  <div className="bg-zinc-50 dark:bg-black/30 p-4 rounded-lg border border-zinc-100 dark:border-white/5">
                    <strong className="text-zinc-800 dark:text-zinc-300">Action Protocol:</strong> Spikes above 4.5 Kurtosis, specifically isolated to the 2x frequency order, strongly correlate with bearing micro-spalling or gear tooth sheer. Schedule immediate maintenance upon landing.
                  </div>
                </section>
              </div>
            </Card>
          </div>
        )}

        {activeTab === "settings" && (
          <div className="flex-1 flex items-start justify-center pt-10">
            <Card className={cn(panelCls, "p-8 max-w-md w-full shadow-lg")}>
              <div className="flex items-center mb-6 pb-4 border-b border-zinc-100 dark:border-white/5">
                <Settings2 className="w-6 h-6 text-blue-600 dark:text-blue-500 mr-3" />
                <h3 className="text-xl font-bold text-zinc-900 dark:text-white">GCS Preferences</h3>
              </div>

              <div className="space-y-6">
                <div className="space-y-3">
                  <label className="text-xs font-bold text-zinc-500 uppercase tracking-widest">Interface Theme</label>
                  <div className="grid grid-cols-2 gap-3">
                    <button
                      onClick={() => setTheme("dark")}
                      className={`flex items-center justify-center p-3 rounded-lg border text-sm font-medium transition-colors ${theme === "dark" ? "bg-blue-600 border-blue-500 text-white" : "bg-zinc-50 border-zinc-200 text-zinc-600 hover:bg-zinc-100 dark:bg-zinc-900/70 dark:border-white/10 dark:text-zinc-300 dark:hover:bg-zinc-800/70"}`}
                    >
                      <Moon className="w-4 h-4 mr-2" /> Tactical Dark
                    </button>
                    <button
                      onClick={() => setTheme("light")}
                      className={`flex items-center justify-center p-3 rounded-lg border text-sm font-medium transition-colors ${theme === "light" ? "bg-blue-600 border-blue-500 text-white" : "bg-zinc-50 border-zinc-200 text-zinc-600 hover:bg-zinc-100 dark:bg-zinc-900/70 dark:border-white/10 dark:text-zinc-300 dark:hover:bg-zinc-800/70"}`}
                    >
                      <Sun className="w-4 h-4 mr-2" /> Daylight Glass
                    </button>
                  </div>
                </div>

                <div className="space-y-3 pt-4 border-t border-zinc-100 dark:border-white/5">
                  <label className="text-xs font-bold text-zinc-500 uppercase tracking-widest flex justify-between">
                    <span>Telemetry Polling Rate</span>
                    <span className="text-blue-600 dark:text-blue-400">{pollingRate} ms</span>
                  </label>
                  <input
                    type="range" min="100" max="2000" step="100"
                    value={pollingRate}
                    onChange={(e) => setPollingRate(Number(e.target.value))}
                    className="w-full accent-blue-600 dark:accent-blue-500 bg-zinc-200 dark:bg-zinc-800 h-1 rounded-full appearance-none cursor-pointer"
                  />
                  <p className="text-[10px] text-zinc-500 leading-tight">Lower polling rates increase data resolution but require higher datalink bandwidth.</p>
                </div>
              </div>
            </Card>
          </div>
        )}

      </div>
    </div>
  );
}