import { Button } from "@/components/ui/button"
import { PenLine, Play, Square, Trash2,FolderUp } from "lucide-react"

interface InventoryControlProps {
  isInventoryRunning: boolean
  isConnected: boolean
  onStart: () => void
  onStop: () => void
  onClear: () => void
  writeEPC?: () => void
  exportCSV?: () => void
}

export function InventoryControl({
  isInventoryRunning,
  isConnected,
  onStart,
  onStop,
  onClear,
  writeEPC,
  exportCSV 
}: InventoryControlProps) {
  return (
    <div className="grid grid-cols-2 gap-3">
     
      <Button
        size="sm"
        onClick={onStart}
        disabled={isInventoryRunning || !isConnected}
        className="w-full"
      >
        <Play className="h-4 w-4 mr-2" />
        Start
      </Button>
      <Button
        variant="destructive"
        size="sm"
        onClick={onStop}
        disabled={!isInventoryRunning}
        className="w-full"
      >
        <Square className="h-4 w-4 mr-2" />
        Stop
      </Button>
      <Button variant="outline" size="sm" onClick={onClear} className="w-full">
        <Trash2 className="h-4 w-4 mr-2" />
        Clear
      </Button>
      <Button variant="outline" size="sm" onClick={exportCSV} className="w-full">
        <FolderUp  className="h-4 w-4 mr-2" />
        Export CSV
      </Button>
      <Button variant="outline" size="sm" onClick={writeEPC} className="w-full">
        <PenLine  className="h-4 w-4 mr-2" />
       Write EPC
      </Button>
    </div>
  )
}
