"use client";

import React, { useState, useEffect } from "react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

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
  const [kurtosis, setKurtosis] = useState<number>(2.9);
  const [alertState, setAlertState] = useState<{ title: string; desc: string } | null>(null);

  useEffect(() => {
    const fetchTelemetry = async () => {
      try {
        const response = await fetch(`http://localhost:8000/api/telemetry?altitude=${altitude}&throttle=${throttle}&fault_mode=${faultMode}`);
        const result = await response.json();

        setHealthIndex(result.analytics.health_index);
        setRulHours(Math.round(result.analytics.health_index * 14.5));
        setKurtosis(result.engine.vibration_kurtosis);

        if (result.analytics.is_anomaly && faultMode === "misfire") {
          setAlertState({ title: "SYS WARN: Z-SCORE ANOMALY", desc: `EGT Variance > 3σ. Z-Score: ${result.analytics.z_score}` });
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
        <span>SYS TIME: {new Date().toISOString()}</span>
      </div>

      <header className="mb-4 flex justify-between items-end">
        <div>
          <h1 className="text-xl font-bold tracking-widest text-zinc-100 uppercase">MALE UAV Propulsion Digital Twin</h1>
          <p className="text-xs font-mono text-zinc-500">PROGNOSTICS & HEALTH MANAGEMENT (PHM) SUBSYSTEM</p>
        </div>
        <div className="text-right">
          <div className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">Mission Reliability</div>
          <div className={`text-2xl font-mono font-bold ${healthIndex < 60 ? 'text-red-500' : healthIndex < 85 ? 'text-amber-400' : 'text-emerald-500'}`}>
            {healthIndex}.00%
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">

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
    </div>
  );
}