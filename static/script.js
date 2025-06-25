
// Socket.IO connection
const socket = io();
let isConnected = false;

// DOM elements
const statusIndicator = document.getElementById("statusIndicator");
const connectionStatus = document.getElementById("connectionStatus");
const connectBtn = document.getElementById("connectBtn");
const disconnectBtn = document.getElementById("disconnectBtn");
const tagsTableBody = document.getElementById("tagsTableBody");
const alertContainer = document.getElementById("alertContainer");

// Tags storage
let tagsData = new Map(); // Map to store tag data: EPC -> {count, antenna, rssi, lastSeen}

// Timer logic
let timerInterval = null;
let timerStart = null;

function startTimer() {
  if (timerInterval) clearInterval(timerInterval);
  timerStart = Date.now();
  timerInterval = setInterval(updateTimer, 1000);
}
function stopTimer() {
  if (timerInterval) clearInterval(timerInterval);
}
function resetTimer() {
  stopTimer();
  document.getElementById("timer").textContent = "00:00:00";
}
function updateTimer() {
  if (!timerStart) return;
  const elapsed = Math.floor((Date.now() - timerStart) / 1000);
  const h = String(Math.floor(elapsed / 3600)).padStart(2, "0");
  const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, "0");
  const s = String(elapsed % 60).padStart(2, "0");
  document.getElementById("timer").textContent = `${h}:${m}:${s}`;
}

// Update connection status
function updateConnectionStatus(connected) {
  isConnected = connected;
  if (connected) {
    statusIndicator.className = "status-indicator status-connected";
    connectionStatus.textContent = "Đã kết nối";
    connectBtn.disabled = true;
    disconnectBtn.disabled = false;
    enableControls();
    // Enable profile and antenna buttons
    document.getElementById("powerBtn").disabled = false;
    document.getElementById("powerInfoBtn").disabled = false;
    document.getElementById("profileBtn").disabled = false;
    document.getElementById("getProfileBtn").disabled = false;
  } else {
    statusIndicator.className = "status-indicator status-disconnected";
    connectionStatus.textContent = "Chưa kết nối";
    connectBtn.disabled = false;
    disconnectBtn.disabled = true;
    disableControls();
    // Disable profile and antenna buttons
    document.getElementById("powerBtn").disabled = true;
    document.getElementById("powerInfoBtn").disabled = true;
    document.getElementById("profileBtn").disabled = true;
    document.getElementById("getProfileBtn").disabled = true;
  }
}

// Enable/disable controls
function enableControls() {
  document.getElementById("infoBtn").disabled = false;
  document.getElementById("startTargetABtn").disabled = false;
  document.getElementById("tagsInventoryBtn").disabled = false;
  document.getElementById("stopBtn").disabled = false;
  document.getElementById("powerBtn").disabled = false;
  document.getElementById("powerInfoBtn").disabled = false;
  document.getElementById("profileBtn").disabled = false;
  document.getElementById("getProfileBtn").disabled = false;
}

function disableControls() {
  document.getElementById("infoBtn").disabled = true;
  document.getElementById("startTargetABtn").disabled = true;
  document.getElementById("tagsInventoryBtn").disabled = true;
  document.getElementById("stopBtn").disabled = true;
  document.getElementById("powerBtn").disabled = true;
  document.getElementById("powerInfoBtn").disabled = true;
  document.getElementById("profileBtn").disabled = true;
  document.getElementById("getProfileBtn").disabled = true;
}

// Show alert
function showAlert(message, type = "info") {
  const alertDiv = document.createElement("div");
  alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
  alertDiv.innerHTML = `
          ${message}
          <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      `;
  alertContainer.appendChild(alertDiv);

  // Auto remove after 5 seconds
  setTimeout(() => {
    if (alertDiv.parentNode) {
      alertDiv.remove();
    }
  }, 5000);
}

// API functions
async function apiCall(url, method = "GET", data = null) {
  try {
    const options = {
      method: method,
      headers: {
        "Content-Type": "application/json",
      },
    };

    if (data) {
      options.body = JSON.stringify(data);
    }

    const response = await fetch(url, options);
    return await response.json();
  } catch (error) {
    console.error("API Error:", error);
    return { success: false, message: "Network error" };
  }
}

// Connect to reader
async function connectReader() {
  const port = document.getElementById("portInput").value;
  const baudrate = parseInt(
    document.getElementById("baudrateInput").value
  );

  showLoading(connectBtn, true);

  const result = await apiCall("/api/connect", "POST", {
    port,
    baudrate,
  });

  showLoading(connectBtn, false);

  if (result.success) {
    updateConnectionStatus(true);
    showAlert(result.message, "success");
    await getReaderInfo();
    await getAntennaPower();
  } else {
    showAlert(result.message, "danger");
  }
}

// Disconnect from reader
async function disconnectReader() {
  const result = await apiCall("/api/disconnect", "POST");

  if (result.success) {
    updateConnectionStatus(false);
    showAlert(result.message, "success");
    document.getElementById("readerInfo").innerHTML =
      '<p class="text-muted">Kết nối để xem thông tin reader</p>';
  } else {
    showAlert(result.message, "danger");
  }
}

// // Get reader info
// async function getReaderInfo() {
//   const result = await apiCall("/api/reader_info");

//   if (result.success) {
//     const info = result.data;
//     document.getElementById("readerInfo").innerHTML = `
//               <div class="row">
//                   <div class="col-6">
//                       <strong>Firmware:</strong> ${
//                         info.firmware_version
//                       }<br>
//                       <strong>Type:</strong> ${info.reader_type}<br>
//                       <strong>Power:</strong> ${info.rf_power} dBm<br>
//                       <strong>Inventory Time:</strong> ${
//                         info.inventory_time
//                       } ms
//                   </div>
//                   <div class="col-6">
//                       <strong>Protocols:</strong><br>
//                       ${info.supported_protocols
//                         .map(
//                           (p) =>
//                             `<span class="badge bg-primary">${p}</span>`
//                         )
//                         .join(" ")}<br>
//                       <strong>Antenna Check:</strong> ${
//                         info.antenna_check
//                       }<br>
//                       <strong>Antenna Config:</strong> 0x${info.antenna_config
//                         .toString(16)
//                         .toUpperCase()}
//                   </div>
//               </div>
//           `;
//   } else {
//     showAlert(result.message, "warning");
//   }
// }

// Start inventory
async function startInventory(target) {
  const result = await apiCall("/api/start_inventory", "POST", {
    target,
  });
  if (result.success) {
    showAlert(result.message, "success");
    document.getElementById("stopBtn").disabled = false;
    startTimer();
  } else {
    showAlert(result.message, "danger");
  }
}

// Stop inventory
async function stopInventory() {
  const result = await apiCall("/api/stop_inventory", "POST");
  if (result.success) {
    showAlert(result.message, "success");
    stopTimer();
  } else {
    showAlert(result.message, "danger");
  }
}

// Set power (for single antenna)
async function setPowerAllAntennas() {
const powers = {
1: parseInt(document.getElementById("powerInput1").value),
2: parseInt(document.getElementById("powerInput2").value),
3: parseInt(document.getElementById("powerInput3").value),
4: parseInt(document.getElementById("powerInput4").value),
};
const preserveConfig = document.getElementById("preserveConfig").checked;
const data = {
powers: powers,
preserve_config: preserveConfig
};
const result = await apiCall("/api/set_power", "POST", data);
if (result.success) {
showAlert("Đã thiết lập công suất cho tất cả antennas!", "success");
await getAntennaPower();
} else {
showAlert(result.message, "danger");
}
}

// Get antenna power (for single antenna)
async function getAntennaPower() {
const result = await apiCall("/api/get_antenna_power");
if (result.success) {
const powerLevels = result.data;
// Fill the input boxes for each antenna
for (let ant = 1; ant <= 4; ant++) {
const input = document.getElementById(`powerInput${ant}`);
if (input && powerLevels[ant] !== undefined) {
  input.value = powerLevels[ant];
}
}

} else {
showAlert(result.message, "warning");
}
}

async function setPowerForAntenna(antenna) {
const power = parseInt(document.getElementById(`powerInput${antenna}`).value);
const preserveConfig = document.getElementById("preserveConfig").checked;
const data = {
power: power,
preserve_config: preserveConfig,
antenna: antenna
};
const result = await apiCall("/api/set_power", "POST", data);
if (result.success) {
showAlert(`Đã thiết lập công suất Antenna ${antenna}: ${power} dBm`, "success");
await getAntennaPower();
} else {
showAlert(result.message, "danger");
}
}

// Set profile
async function setProfile() {
  const profileNum = parseInt(
    document.getElementById("profileSelect").value
  );
  const saveOnPowerDown = document.getElementById("saveProfile").checked;

  const result = await apiCall("/api/set_profile", "POST", {
    profile_num: profileNum,
    save_on_power_down: saveOnPowerDown,
  });

  if (result.success) {
    showAlert(result.message, "success");
  } else {
    showAlert(result.message, "danger");
  }
}

// Get profile
async function getProfile() {
  const result = await apiCall("/api/get_profile");

  if (result.success) {
    const profile = result.data.profile;
    document.getElementById("profileSelect").value = profile;
    showAlert(`Profile hiện tại: ${profile}`, "info");
  } else {
    showAlert(result.message, "warning");
  }
}

// Update tags table
function updateTagsTable() {
  if (tagsData.size === 0) {
    tagsTableBody.innerHTML =
      '<tr><td colspan="5" class="text-center text-muted">Chưa có tags được phát hiện</td></tr>';
    document.getElementById("uniqueTags").textContent = "0";
    document.getElementById("totalTags").textContent = "0";
    return;
  }

  // Clear table
  tagsTableBody.innerHTML = "";

  // Sort tags by count (descending)
  const sortedTags = Array.from(tagsData.entries()).sort(
    (a, b) => b[1].count - a[1].count
  );

  // Add rows
  sortedTags.forEach(([epc, data]) => {
    const row = document.createElement("tr");
    row.innerHTML = `
              <td><span class="tag-epc">${epc}</span></td>
              <td><span class="badge bg-primary">${data.count}</span></td>
              <td><span class="antenna-badge">Ant ${data.antenna}</span></td>
              <td><span class="rssi-badge">${data.rssi} dBm</span></td>
              <td><span class="timestamp">${data.lastSeen}</span></td>
          `;
    tagsTableBody.appendChild(row);
  });

  // Update unique tags count
  document.getElementById("uniqueTags").textContent = tagsData.size;

  // Tính lại Total Tags (tổng count)
  let totalCount = 0;
  tagsData.forEach((data) => {
    totalCount += data.count;
  });
  document.getElementById("totalTags").textContent = totalCount;
}

// Clear tags
function clearTags() {
  tagsData.clear();
  updateTagsTable();
  resetTimer();
}

// Reset reader
async function resetReader() {
  try {
    const response = await fetch("/api/reset_reader", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    });
    const result = await response.json();
    if (result.success) {
      showAlert(result.message, "success");
      // Clear tags display
      clearTags();
    } else {
      showAlert(result.message, "danger");
    }
  } catch (error) {
    showAlert(`Lỗi reset reader: ${error}`, "danger");
  }
}

// Show loading state
function showLoading(button, loading) {
  const loadingSpan = button.querySelector(".loading");
  const icon = button.querySelector("i");

  if (loading) {
    loadingSpan.style.display = "inline-block";
    icon.style.display = "none";
    button.disabled = true;
  } else {
    loadingSpan.style.display = "none";
    icon.style.display = "inline-block";
    button.disabled = false;
  }
}

// // Event listeners
// document
//   .getElementById("powerInput")
//   .addEventListener("input", function () {
//     document.getElementById("powerValue").textContent = this.value;
//   });

// Socket.IO events
socket.on("connect", function () {
  console.log("🔌 Connected to server via WebSocket");
});


socket.on("disconnect", function () {
  console.log("🔌 Disconnected from server");
});


socket.on("tag_detected", function (tagData) {
  console.log("🔍 WebSocket tag_detected received:", tagData);

  // Update tags data
  const epc = tagData.epc;
  if (tagsData.has(epc)) {
    // Update existing tag
    const existing = tagsData.get(epc);
    existing.count++;
    existing.lastSeen = tagData.timestamp;
    // Update RSSI if new one is stronger
    if (tagData.rssi > existing.rssi) {
      existing.rssi = tagData.rssi;
    }
    // Update antenna if different
    if (existing.antenna !== tagData.antenna) {
      existing.antenna = `${existing.antenna}, ${tagData.antenna}`;
    }
  } else {
    // Add new tag
    tagsData.set(epc, {
      count: 1,
      antenna: tagData.antenna,
      rssi: tagData.rssi,
      lastSeen: tagData.timestamp,
    });
  }
  
  updateTagsTable();
});

socket.on("status", function (data) {
  console.log("📡 Status message received:", data.message);
});

// Initialize
updateConnectionStatus(false);

function openTagsInventoryModal() {
  var modal = new bootstrap.Modal(
    document.getElementById("tagsInventoryModal")
  );
  modal.show();
}

async function startTagsInventory() {
  const q_value = parseInt(document.getElementById("qValueInput").value);
  const session = parseInt(document.getElementById("sessionInput").value);
  const antenna = 1; // Mặc định sử dụng antenna 1
  const scan_time = parseInt(
    document.getElementById("scanTimeInput").value
  );

  const result = await apiCall("/api/tags_inventory", "POST", {
    q_value,
    session,
    antenna,
    scan_time,
  });
  if (result.success) {
    showAlert(result.message, "success");
    document.getElementById("stopBtn").disabled = false;
    startTimer();
    // Đóng modal
    var modal = bootstrap.Modal.getInstance(
      document.getElementById("tagsInventoryModal")
    );
    modal.hide();
  } else {
    showAlert(result.message, "danger");
  }
}

async function stopTagsInventory() {
  const result = await apiCall("/api/stop_tags_inventory", "POST");
  if (result.success) {
    showAlert(result.message, "success");
    document.getElementById("stopBtn").disabled = true;
    stopTimer();
  } else {
    showAlert(result.message, "danger");
  }
}
