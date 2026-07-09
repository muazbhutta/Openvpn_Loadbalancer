<div align="center">

# 🌐 OpenVPN Load Balancer

### ⚡ A high-performance, asynchronous UDP load balancer for OpenVPN servers

<br>

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![OpenVPN](https://img.shields.io/badge/OpenVPN-Compatible-EA7E20?style=for-the-badge&logo=openvpn&logoColor=white)](https://openvpn.net/)

[![Asyncio](https://img.shields.io/badge/Built%20With-asyncio-2E8B57?style=flat-square&logo=python&logoColor=white)](https://docs.python.org/3/library/asyncio.html)
[![Protocol](https://img.shields.io/badge/Protocol-UDP-FF6F00?style=flat-square)](https://en.wikipedia.org/wiki/User_Datagram_Protocol)
[![Platform](https://img.shields.io/badge/Platform-Linux-FCC624?style=flat-square&logo=linux&logoColor=black)](https://www.linux.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-success?style=flat-square)](#)
[![Dependencies](https://img.shields.io/badge/Dependencies-None-brightgreen?style=flat-square)](#)

<br>

*Distribute VPN traffic across multiple servers in multiple regions — with health checks, session stickiness, and automatic failover.*

[📖 What Is It?](#-what-is-it) •
[🚀 How to Use](#-how-to-use) •
[✨ Benefits](#-benefits) •
[⚙️ How It Works](#%EF%B8%8F-how-it-works)

</div>

---

## 📖 What Is It?

When you run a VPN service, a single OpenVPN server quickly becomes a bottleneck. **OpenVPN Load Balancer** sits in front of a pool of OpenVPN servers and acts as a smart traffic director:

- 🎯 Clients connect to **one public address** (the load balancer) instead of individual servers.
- 🔀 The balancer forwards each client's UDP packets to a **healthy, non-overloaded** upstream server using **round-robin scheduling**.
- 🔁 Return traffic from the server is relayed back to the correct client **transparently**.

Each region gets its own listening port and its own independent server pool:

<div align="center">

| 🌍 Region     | 🔌 Listening Port | 🖥️ Upstream Servers |
|:-------------:|:-----------------:|:-------------------:|
| 🇺🇸 USA        | `1194`            | 3                   |
| 🇬🇧 UK         | `1195`            | 3                   |
| 🇸🇬 Singapore  | `1196`            | 3                   |
| 🇩🇪 Germany    | `1197`            | 3                   |

</div>

---

## 🚀 How to Use

### 📋 Prerequisites

- 🐍 **Python 3.8+** — no external packages required, everything is in the standard library
- 🐧 A **Linux host** — the health check uses `ping -c` / `-W` flags
- 🔐 One or more upstream **OpenVPN servers** running in **UDP mode**

### 1️⃣ Clone the repository

```bash
git clone https://github.com/<your-username>/openvpn-load-balancer.git
cd openvpn-load-balancer
```

### 2️⃣ Configure your server pools

Open `openvpn_load_balancing.py` and replace the placeholder IPs with your real OpenVPN server addresses:

```python
USA_SERVERS = [
    ("your.server.ip.1", 1194),
    ("your.server.ip.2", 1194),
    ("your.server.ip.3", 1194),
]
```

### 3️⃣ Tune the settings *(optional)*

```python
MAX_CLIENTS_PER_SERVER = 100   # Max concurrent clients per upstream server
IDLE_TIMEOUT_SECONDS   = 300   # Release a client flow after 5 min of silence
HEALTHCHECK_INTERVAL   = 15    # Ping every server every 15 seconds
HEALTHCHECK_TIMEOUT    = 3     # Ping timeout per check (seconds)
```

### 4️⃣ Run it

```bash
python3 openvpn_load_balancing.py
```

You should see output like:

```
2026-07-09 12:00:00 [INFO] [ClientProtocol] Listening on ('0.0.0.0', 1194)
2026-07-09 12:00:00 [INFO] USA region load balancer running on port 1194...
2026-07-09 12:00:01 [INFO] Assigned client ('203.0.113.7', 51820) to server ('102.123.112.2', 1194) (usage=1/100, healthy=True)
```

### 5️⃣ Point your clients at the balancer

In each client's `.ovpn` profile, set the remote to the load balancer's public IP and the port for the desired region:

```
remote <load-balancer-ip> 1194   # 🇺🇸 USA
remote <load-balancer-ip> 1195   # 🇬🇧 UK
remote <load-balancer-ip> 1196   # 🇸🇬 Singapore
remote <load-balancer-ip> 1197   # 🇩🇪 Germany
```

> 💡 **Tip:** Run it as a `systemd` service in production so it restarts automatically on failure.

---

## ✨ Benefits

| | Benefit | Description |
|:---:|---|---|
| 🪶 | **Zero dependencies** | Pure Python standard library (`asyncio`, `socket`, `logging`) — nothing to `pip install` |
| ⚡ | **Fully asynchronous** | A single event loop handles thousands of UDP flows without threads or per-connection overhead |
| 📈 | **Horizontal scaling** | Add capacity by simply appending servers to a region's list |
| ❤️ | **Automatic failover** | Unhealthy servers are detected within seconds and skipped; they rejoin automatically once reachable |
| 📌 | **Session stickiness** | A client always talks to the same upstream server — essential for OpenVPN's stateful UDP sessions |
| 🚦 | **Overload protection** | The `MAX_CLIENTS_PER_SERVER` cap prevents any single server from being flooded |
| 🧹 | **Self-cleaning** | Idle flows are released after a timeout, reclaiming capacity from disconnected clients |
| 🌍 | **Multi-region by design** | Each region runs its own isolated balancer, port, and health checker in one process |
| 🔍 | **Transparent to OpenVPN** | No changes needed on your servers — the balancer just relays raw UDP datagrams |

---

## ⚙️ How It Works

### 🏗️ Architecture

```
                          ┌──────────────────────────────┐
   VPN Clients            │        Load Balancer         │        OpenVPN Servers
                          │                              │
  client A ──UDP:1194──►  │  ClientProtocol (per region) │  ──►  Server 1  (USA)
  client B ──UDP:1194──►  │        │ round-robin         │  ──►  Server 2  (USA)
  client C ──UDP:1195──►  │        ▼                     │  ──►  Server 3  (USA)
                          │  ServerProtocol (per server) │
                          │        ▲                     │  ──►  Server 1  (UK)
                          │  HealthCheck task (ping)     │  ──►  ...
                          └──────────────────────────────┘
```

### 🧩 Core Components

#### 🧠 `LoadBalancer` — the brain
Keeps all the state for one region: the server list, per-server client counts (`server_usage`), health flags (`server_health`), the round-robin pointer, a `client → server` assignment map, and a `flow_map` recording the last activity timestamp of every `(client_ip, client_port, server_ip, server_port)` flow.

#### 🚪 `ClientProtocol` — the front door
An `asyncio.DatagramProtocol` bound to the region's public port (e.g. `0.0.0.0:1194`). When a packet arrives from a client:

1. ♻️ If the client is already assigned to a server, reuse that assignment (**stickiness**)
2. 🔄 Otherwise, pick the next server via **round-robin**, skipping servers that are unhealthy or at capacity
3. ⏱️ Record/refresh the flow's activity timestamp
4. 📤 Forward the datagram to the chosen server through its `ServerProtocol`

#### 🔙 `ServerProtocol` — the back door
One persistent UDP socket per upstream server. When the server replies, the packet is matched against `flow_map` to find which client it belongs to, and it's sent back to that client from the original listening socket — so from the client's perspective, all traffic comes from the one address it connected to.

#### ❤️‍🩹 Health Check Task
Every `HEALTHCHECK_INTERVAL` seconds, each server is pinged asynchronously (ICMP). A failed ping marks the server **UNHEALTHY**: new clients are steered away from it, but existing flows are left alone until they idle out. Once the server responds again, it is marked **HEALTHY** and rejoins the rotation.

#### 🧹 Idle-Flow Reaper
The main loop wakes every 5 seconds and scans `flow_map`. Any flow silent for longer than `IDLE_TIMEOUT_SECONDS` is released: its record is deleted, the server's usage counter is decremented, and the client-to-server mapping is removed — freeing that slot for a new client.

### 📦 Packet Lifecycle (End to End)

```
Client packet ──► ClientProtocol.datagram_received()
                      │
                      ├─ assign_server()  ── round-robin over healthy, non-full servers
                      ├─ add_flow() / update_flow_activity()
                      └─ ServerProtocol.sendto_server() ──► OpenVPN server

Server reply  ──► ServerProtocol.datagram_received()
                      │
                      └─ ClientProtocol.handle_server_packet()
                             ├─ look up flow in flow_map
                             └─ transport.sendto(data, client) ──► Client
```

---

## ⚠️ Notes & Limitations

- 🚫 The health check uses **ICMP ping** — networks that block ICMP need a different probe (e.g., a UDP probe to the OpenVPN port)
- 🐧 The `ping -c` / `-W` flags are **Linux-style**; on Windows, adapt them to `-n` / `-w`
- 🏷️ The sample IPs in the source are **placeholders** — replace them with your real servers before running
- 📡 This balances at the **UDP datagram level**; it does not inspect or terminate the OpenVPN protocol itself

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

## 🤝 Contributing

Contributions are welcome! Feel free to open an issue or submit a pull request for weighted balancing, better health probes, config file support, or Windows compatibility.

---

<div align="center">

**⭐ If this project helped you, consider giving it a star! ⭐**

Made with 🐍 Python & ❤️

</div>
