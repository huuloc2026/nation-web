import { Button } from "@/components/ui/button"
import { Settings, Play, Square, Trash2 } from "lucide-react"

interface InventoryControlProps {
  isInventoryRunning: boolean
  isConnected: boolean
  onStart: () => void
  onStop: () => void
  onClear: () => void
}

export function InventoryControl({
  isInventoryRunning,
  isConnected,
  onStart,
  onStop,
  onClear,
}: InventoryControlProps) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <Button variant="outline" size="sm" className="w-full">
        <Settings className="h-4 w-4 mr-2" />
        Setting
      </Button>
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
    </div>
  )
}
