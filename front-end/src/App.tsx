import { useState, useEffect, useRef } from "react"
import { Menu } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet"
import { Sidebar } from "./components/Sidebar"
import { TagTable } from "./components/TagTable"
import { CheckWriteEPC, connectReader, disconnectReader, startInventory, stopInventory, WriteEPCtag } from "./api/rfid"
import { toast } from "sonner"
import { io, Socket } from "socket.io-client"
import * as XLSX from "xlsx"

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { InventoryControl } from "./components/InventoryControl"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@radix-ui/react-label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { BAUD_RATE_OPTIONS, SERIPORT, SOCKET_URL } from "./utils/constant"

import "./AppDialog.css" // Add this import at the top (create this CSS file if not exist)

// Types
export interface Tag {
  id: number
  epc: string
  count: number
  antenna: number | string
  rssi: number
  lastSeen: string
}

export interface AntennaSettings {
  [key: string]: boolean
  antenna1: boolean
  antenna2: boolean
  antenna3: boolean
  antenna4: boolean
}

export default function Dashboard() {
  const [isConnected, setIsConnected] = useState(false)
  const [serialPort, setSerialPort] = useState(SERIPORT)
  const [baudRate, setBaudRate] = useState(BAUD_RATE_OPTIONS)
  const [detectedTags, setDetectedTags] = useState(0)
  const [totalTags, setTotalTags] = useState(0)
  const [timer, setTimer] = useState("00:00:00")
  const [isInventoryRunning, setIsInventoryRunning] = useState(false)
  const [tags, setTags] = useState<Tag[]>([])
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [elapsedMs, setElapsedMs] = useState(0)

  const [writeDialogOpen, setWriteDialogOpen] = useState(false)
  const [newEpcTags, setNewEpcTags] = useState<string>("")
  const [writeResults, setWriteResults] = useState<any[]>([])
  const [writeLoading, setWriteLoading] = useState(false)

  // For file upload and write
  const [fileEpcRows, setFileEpcRows] = useState<string[]>([])
  const [fileLog, setFileLog] = useState<{ epc: string; success: boolean; result_msg: string }[]>([])
  const [fileLoading, setFileLoading] = useState(false)

  const [selectedAntennas, setSelectedAntennas] = useState<number[]>([1])
  // Antenna settings
  const [antennaSettings, setAntennaSettings] = useState<AntennaSettings>({
    antenna1: true,
    antenna2: false,
    antenna3: false,
    antenna4: false,
  })

  // --- WebSocket state ---
  const socketRef = useRef<Socket | null>(null)
  const tagMapRef = useRef<Map<string, Tag>>(new Map())

  useEffect(() => {
    const socket = io(SOCKET_URL, {
      transports: ["websocket"],
      path: "/socket.io",
      withCredentials: false,
    });
  
    socketRef.current = socket;
  
    const handleTagDetected = (tagData: any) => {
      const map = tagMapRef.current;
      const { epc } = tagData;
      if (map.has(epc)) {
        const t = map.get(epc)!;
        t.count += 1;
        t.lastSeen = tagData.timestamp;
        t.rssi = Math.max(t.rssi, tagData.rssi);
        const antennas = new Set(
          `${t.antenna}`.split(",").map(a=>a.trim()).filter(Boolean)
        );
        antennas.add(String(tagData.antenna));
        t.antenna = Array.from(antennas).join(", ");
      } else {
        map.set(epc, {
          id: map.size + 1,
          epc,
          count: 1,
          antenna: tagData.antenna,
          rssi: tagData.rssi,
          lastSeen: tagData.timestamp,
        });
      }
      const arr = Array.from(map.values());
      setTags(arr);
      setDetectedTags(arr.length);
      setTotalTags(arr.reduce((s, t) => s + t.count, 0));
    };
  
    socket.on("tag_detected", handleTagDetected);
    socket.on("inventory_end", () => setIsInventoryRunning(false));
  
    return () => {
      socket.off("tag_detected", handleTagDetected); 
      socket.disconnect();                           
      socketRef.current = null;
    };
  }, []);
  

  // Timer effect
  useEffect(() => {
    let interval: ReturnType<typeof setInterval>
    let startTime: number
    if (isInventoryRunning) {
      startTime = Date.now()
      interval = setInterval(() => {
        const elapsed = Date.now() - startTime + elapsedMs
        const hours = Math.floor(elapsed / 3600000)
        const minutes = Math.floor((elapsed % 3600000) / 60000)
        const seconds = Math.floor((elapsed % 60000) / 1000)
        setTimer(
          `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`,
        )
      }, 1000)
    }
    return () => clearInterval(interval)
  }, [isInventoryRunning, elapsedMs])

  // --- Clear tags on inventory start/stop ---
  const handleStartInventory = async () => {
    tagMapRef.current.clear()
    setTags([])
    setDetectedTags(0)
    setTotalTags(0)
    setIsInventoryRunning(true)
    await startInventory(selectedAntennas)
    // Optionally handle result for user feedback
  }

  const handleStopInventory = async () => {
    setIsInventoryRunning(false)
    // Save elapsed time
    const [h, m, s] = timer.split(":").map(Number)
    setElapsedMs(h * 3600000 + m * 60000 + s * 1000)
    await stopInventory()
    // Optionally handle result for user feedback
  }

  const handleClear = async () => {
    tagMapRef.current.clear()
    setTags([])
    setDetectedTags(0)
    setTotalTags(0)
    setTimer("00:00:00")
    setElapsedMs(0)
    
    setIsInventoryRunning(false)
  }

  const handleConnect = async () => {
    if (!isConnected) {
      const result = await connectReader(serialPort, Number(baudRate))
      if (result.success) setIsConnected(true)
      // handle result.message for user feedback
    } else {
      const result = await disconnectReader()
      if (result.success) setIsConnected(false)
      // handle result.message for user feedback
    }
  }

  const handleGetPower = async () => {
    try {
      toast("Đã lấy thông tin công suất antennas.", {
        description: "Get Power",
      })
    } catch (e) {
      toast("Không thể lấy thông tin công suất.", {
        description: "Lỗi",
        style: { background: "#ef4444", color: "#fff" },
      })
    }
  }

  const handleSetPower = async () => {
    try {
      // Replace with actual set power logic if available
      toast("Đã thiết lập công suất antennas.", {
        description: "Set Power",
      })
    } catch (e) {
      toast("Không thể thiết lập công suất.", {
        description: "Lỗi",
        style: { background: "#ef4444", color: "#fff" },
      })
    }
  }

  const handleAntennaChange = (antenna: keyof AntennaSettings, checked: boolean) => {
    setAntennaSettings((prev) => ({
      ...prev,
      [antenna]: checked,
    }))
  }

  // Handle file upload and parse XLSX/CSV
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (evt) => {
      const data = evt.target?.result
      if (!data) return
      let rows: string[] = []
      if (file.name.endsWith(".csv")) {
        // Simple CSV: split by line, take first column
        const text = data as string
        rows = text
          .split(/\r?\n/)
          .map(line => line.split(",")[0]?.trim())
          .filter(Boolean)
      } else {
        // XLSX: use SheetJS
        const workbook = XLSX.read(data, { type: "binary" })
        const sheet = workbook.Sheets[workbook.SheetNames[0]]
        const json = XLSX.utils.sheet_to_json<{ [k: string]: any }>(sheet, { header: 1 })
        rows = (json as any[][])
          .map(row => row[0]?.toString().trim())
          .filter(Boolean)
      }
      setFileEpcRows(rows.slice(0, 100)) // limit to 100 for safety
      setFileLog([])
    }
    if (file.name.endsWith(".csv")) {
      reader.readAsText(file)
    } else {
      reader.readAsBinaryString(file)
    }
  }

  // Write a single EPC from file table
  const handleWriteFileEpc = async (epc: string) => {
    setFileLoading(true)
    try {
      const params = {
        antennaMask: 1,
        dataArea: 1,
        startWord: 2,
        epcHex: epc.toUpperCase(),
      }
      const data = await WriteEPCtag(
        params.antennaMask,
        params.dataArea,
        params.startWord,
        params.epcHex,
        undefined,
        undefined,
        1
      )
      setFileLog(prev => [
        ...prev,
        { epc, success: data.success, result_msg: data.result_msg || data.message }
      ])
      toast(data.success ? "Ghi thành công" : "Ghi thất bại", { description: epc })
    } catch (e: any) {
      setFileLog(prev => [
        ...prev,
        { epc, success: false, result_msg: e?.message || "Exception" }
      ])
      toast("Ghi thất bại", { description: epc, style: { background: "#ef4444", color: "#fff" } })
    }
    setFileLoading(false)
  }

  const handleStartWrite = async () => {
    setWriteLoading(true)
    setWriteResults([])
    const epcList = newEpcTags
      .split("\n")
      .map(e => e.trim())
      .filter(e => e.length > 0)
    if (epcList.length === 0) {
      toast("Vui lòng nhập ít nhất 1 EPC mới", { style: { background: "#ef4444", color: "#fff" } })
      setWriteLoading(false)
      return
    }
    const results: any[] = []
    for (const epc of epcList) {
      try {
        const params = {
          antennaMask: 1,
          dataArea: 1,
          startWord: 2,
          epcHex: epc.toUpperCase(),
        }
        // WriteEPCtag API expects single EPC, match_epc can be null for auto
        const data = await WriteEPCtag(
          params.antennaMask,
          params.dataArea,
          params.startWord,
          params.epcHex,
          undefined,
          undefined,
          1 // timeout=1s for fast batch
        )
        results.push({
          epc,
          ...data,
        })
      } catch (e: any) {
        results.push({
          epc,
          success: false,
          result_code: -99,
          result_msg: e?.message || "Exception",
        })
      }
      // Optional: small delay between writes
      await new Promise(res => setTimeout(res, 200))
    }
    setWriteResults(results)
    setWriteLoading(false)
    toast("Đã ghi xong danh sách EPC", { description: "Batch Write" })
  }

  const handleCheckWrite = async (epcHex:string) => {
    // const data = await CheckWriteEPC(epcHex,1)
    // if (data.success) {
    //   toast("Kiểm tra ghi thành công", { description: "Check Write" })
    //   setWriteResults(data.results || [])
    // } else {
    //   toast("Kiểm tra ghi thất bại: " + data.message, {
    //     description: "Check Write",
    //     style: { background: "#ef4444", color: "#fff" },
    //   })
    // }
    toast("Chức năng kiểm tra ghi chưa được triển khai", {
      description: "Check Write",
      style: { background: "#fff", color: "#111" },
    })
  }

  return (
    <div className="flex h-screen bg-background">
      {/* Desktop Sidebar */}
      <div className="hidden lg:block">
        <Sidebar
          isConnected={isConnected}
          serialPort={serialPort}
          setSerialPort={setSerialPort}
          baudRate={baudRate}
          setBaudRate={setBaudRate}
          handleConnect={handleConnect}
          antennaSettings={antennaSettings}
          setAntennaSettings={setAntennaSettings}
          handleAntennaChange={handleAntennaChange}
          onSetAntenna={(ants: number[]) => setSelectedAntennas(ants)}
        />
      </div>

      {/* Mobile Sidebar */}
      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left" className="p-0 w-80">
          <Sidebar
            isConnected={isConnected}
            serialPort={serialPort}
            setSerialPort={setSerialPort}
            baudRate={baudRate}
            setBaudRate={setBaudRate}
            handleConnect={handleConnect}
            antennaSettings={antennaSettings}
            setAntennaSettings={setAntennaSettings}
            handleAntennaChange={handleAntennaChange}
            handleGetPower={handleGetPower}
            handleSetPower={handleSetPower}
            onSetAntenna={(ants: number[]) => setSelectedAntennas(ants)}
          />
        </SheetContent>
      </Sheet>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="flex h-14 items-center gap-4 border-b bg-background px-4 lg:px-6">
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setSidebarOpen(true)}>
                <Menu className="h-5 w-5" />
                <span className="sr-only">Toggle sidebar</span>
              </Button>
            </SheetTrigger>
          </Sheet>
          <div className="flex-1">
            <h1 className="text-lg font-semibold">Nation Dashboard</h1>
          </div>
        </header>

        {/* Main Layout: Sidebar + Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Right Main Content */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Top Section: Detected Tags + Control Buttons */}
            <div className="border-b bg-background p-4">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Detected Tags Panel */}
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg">Detected Tags</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-3 gap-4 text-center">
                      <div className="space-y-1">
                        <div className="text-2xl font-bold text-primary">{detectedTags}</div>
                        <div className="text-xs text-muted-foreground">Detected</div>
                      </div>
                      <div className="space-y-1">
                        <div className="text-2xl font-bold">{totalTags}</div>
                        <div className="text-xs text-muted-foreground">Total</div>
                      </div>
                      <div className="space-y-1">
                        <div className="text-lg font-mono font-bold tracking-wider">{timer}</div>
                        <div className="text-xs text-muted-foreground">Timer</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Inventory Control */}
                <InventoryControl
                  isInventoryRunning={isInventoryRunning}
                  isConnected={isConnected}
                  onStart={handleStartInventory}
                  onStop={handleStopInventory}
                  onClear={handleClear}
                  writeEPC={() => setWriteDialogOpen(true)}
                />
              </div>
            </div>

            {/* Bottom Section: Tags Table */}
            <div className="flex-1 p-4 overflow-auto">
              {tags.length === 0 ? (
                <div className="text-center text-muted-foreground py-8">
                  No EPC tags detected
                </div>
              ) : (
                <TagTable tags={tags} />
              )}
            </div>

            {/* --- File Upload & Write EPC Dialog Section --- */}
            <Dialog open={writeDialogOpen} onOpenChange={setWriteDialogOpen}>
              <DialogContent className="custom-dialog-content">
                <DialogHeader>
                  <DialogTitle>Ghi nhiều EPC vào Tag / Upload file EPC</DialogTitle>
                </DialogHeader>
                <DialogDescription>
                  {/* <div className="space-y-2">
                    <Label htmlFor="epc-list-input">Danh sách EPC mới (mỗi dòng 1 EPC)</Label>
                    <textarea
                      id="epc-list-input"
                      value={newEpcTags}
                      onChange={e => setNewEpcTags(e.target.value)}
                      placeholder="Nhập mỗi EPC trên 1 dòng"
                      rows={6}
                      className="w-full border rounded px-2 py-1 text-sm font-mono"
                      disabled={writeLoading}
                    />
                  </div> */}
                  <div className="my-4">
                    <div className="mb-2 text-black font-semibold"> Upload file EPC (xlsx/csv)</div>
             
                    <input
                    className="w-full text-sm  rounded border border-gray-300 cursor-pointer focus:outline-none"
                    type="file"
                    accept=".csv, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.ms-excel"
                    onChange={handleFileChange}
                    disabled={fileLoading}
                  />
                
                  </div>
                  {fileEpcRows.length > 0 && (
                    <div className="mt-4">
                      <div className="mb-2 font-medium">Danh sách EPC từ file:</div>
                      <table className="w-full text-xs text-black border mb-2">
                        <thead>
                          <tr>
                            <th className="border px-2 py-1">Number</th>
                            <th className="border px-2 py-1">EPC (hex)</th>
                            <th className="border py-2 ">Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {fileEpcRows.map((epc, idx) => (
                            <tr key={idx}>
                              <td className="border px-2 py-1">{idx + 1}</td>
                              <td className="border px-2 py-1 font-semibold">{epc}</td>
                              <td className="border px-2 py-1">
                                <Button
                                  size="sm"
                                  onClick={() => handleWriteFileEpc(epc)}
                                  disabled={fileLoading}
                                >
                                  Write
                                </Button>
                                <Button
                    variant="outline"
                    onClick={() => handleCheckWrite(newEpcTags)}
                    disabled={writeLoading}
                  >
                    Check
                  </Button>
                              </td>
                              
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <div className="mb-2 font-medium">Log kết quả ghi:</div>
                      <table className="w-full text-xs border">
                        <thead>
                          <tr>
                            <th className="border px-2 py-1">EPC</th>
                            <th className="border px-2 py-1">Result</th>
                            <th className="border px-2 py-1">Message</th>
                          </tr>
                        </thead>
                        <tbody>
                          {fileLog.map((log, idx) => (
                            <tr key={idx}>
                              <td className="border px-2 py-1 font-mono">{log.epc}</td>
                              <td className="border px-2 py-1">{log.success ? "✅" : "❌"}</td>
                              <td className="border px-2 py-1">{log.result_msg}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </DialogDescription>
                <DialogFooter>
                  {/* <Button
                    onClick={handleStartWrite}
                    disabled={writeLoading || (!newEpcTags.trim() && fileEpcRows.length === 0)}
                  >
                    {writeLoading ? "Đang ghi..." : "Start Write"}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => handleCheckWrite(newEpcTags)}
                    disabled={writeLoading}
                  >
                    Check
                  </Button> */}
                  <Button variant="outline" onClick={() => setWriteDialogOpen(false)} disabled={writeLoading}>
                    Đóng
                  </Button>
                </DialogFooter>
                {writeResults.length > 0 && (
                  <div className="mt-4">
                    <div className="font-semibold mb-2">Kết quả ghi EPC:</div>
                    <table className="w-full text-xs border">
                      <thead>
                        <tr>
                          <th className="border px-2 py-1">EPC</th>
                          <th className="border px-2 py-1">Result</th>
                          <th className="border px-2 py-1">Message</th>
                        </tr>
                      </thead>
                      <tbody>
                        {writeResults.map((r, i) => (
                          <tr key={i}>
                            <td className="border px-2 py-1 font-mono">{r.epc}</td>
                            <td className="border px-2 py-1">{r.success ? "✅" : "❌"}</td>
                            <td className="border px-2 py-1">{r.result_msg || r.message}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>
    </div>
  )
}
