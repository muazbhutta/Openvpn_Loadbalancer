# 🌐 OpenVPN UDP Load Balancer

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)
![Asyncio](https://img.shields.io/badge/Built%20with-asyncio-green)
![Protocol](https://img.shields.io/badge/Protocol-UDP-orange)
![OpenVPN](https://img.shields.io/badge/OpenVPN-Compatible-EA7E20?logo=openvpn&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Linux-lightgrey?logo=linux&logoColor=black)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Status](https://img.shields.io/badge/Status-Active-success)

A lightweight, dependency-free **UDP load balancer for OpenVPN servers**, written in pure Python with `asyncio`. It distributes incoming VPN client traffic across multiple upstream OpenVPN servers per region (USA, UK, Singapore, Germany) using **round-robin scheduling**, with built-in **health checks**, **session stickiness**, and **idle-flow cleanup**.

---

## 📖 What Is It?

When you run a VPN service, a single OpenVPN server quickly becomes a bottleneck. This project sits in front of a pool of OpenVPN servers and acts as a smart traffic director:

- Clients connect to **one public address** (the load balancer) instead of individual servers.
- The balancer forwards each client's UDP packets to a healthy, non-overloaded upstream server.
- Return traffic from the server is relayed back to the correct client transparently.

Each region gets its own listening port and its own independent server pool:

| Region       | Listening Port | Upstream Servers |
|--------------|:--------------:|:----------------:|
| 🇺🇸 USA       | `1194`         | 3                |
| 🇬🇧 UK        | `1195`         | 3                |
| 🇸🇬 Singapore | `1196`         | 3                |
| 🇩🇪 Germany   | `1197`         | 3                |

---

## 🚀 How to Use

### Prerequisites

- **Python 3.8+** (no external packages required — everything is in the standard library)
- A **Linux host** (the health check uses `ping -c`/`-W` flags)
- One or more upstream OpenVPN servers running in **UDP mode**

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/openvpn-load-balancer.git
cd openvpn-load-balancer
```

### 2. Configure your server pools

Open `openvpn_load_balancing.py` and replace the placeholder IPs with your real OpenVPN server addresses:

```python
USA_SERVERS = [
    ("your.server.ip.1", 1194),
    ("your.server.ip.2", 1194),
    ("your.server.ip.3", 1194),
]
```

### 3. Tune the settings (optional)

```python
MAX_CLIENTS_PER_SERVER = 100   # Max concurrent clients per upstream server
IDLE_TIMEOUT_SECONDS   = 300   # Release a client flow after 5 min of silence
HEALTHCHECK_INTERVAL   = 15    # Ping every server every 15 seconds
HEALTHCHECK_TIMEOUT    = 3     # Ping timeout per check (seconds)
```

### 4. Run it

```bash
python3 openvpn_load_balancing.py
```

You should see output like:

```
2026-07-09 12:00:00 [INFO] [ClientProtocol] Listening on ('0.0.0.0', 1194)
2026-07-09 12:00:00 [INFO] USA region load balancer running on port 1194...
2026-07-09 12:00:01 [INFO] Assigned client ('203.0.113.7', 51820) to server ('102.123.112.2', 1194) (usage=1/100, healthy=True)
```

### 5. Point your clients at the balancer

In each client's `.ovpn` profile, set the remote to the load balancer's public IP and the port for the desired region:

```
remote <load-balancer-ip> 1194   # USA
remote <load-balancer-ip> 1195   # UK
remote <load-balancer-ip> 1196   # Singapore
remote <load-balancer-ip> 1197   # Germany
```

> 💡 **Tip:** Run it as a `systemd` service in production so it restarts automatically on failure.

---

## ✨ Benefits

- **🪶 Zero dependencies** — pure Python standard library (`asyncio`, `socket`, `logging`). Nothing to `pip install`.
- **⚡ Fully asynchronous** — a single event loop handles thousands of UDP flows without threads or per-connection overhead.
- **📈 Horizontal scaling** — add capacity by simply appending servers to a region's list.
- **❤️ Automatic failover** — unhealthy servers are detected within seconds and skipped for new clients; they rejoin the pool automatically once reachable again.
- **📌 Session stickiness** — a client always talks to the same upstream server, which is essential for OpenVPN's stateful UDP sessions (handshakes and tunnels would break otherwise).
- **🚦 Overload protection** — the `MAX_CLIENTS_PER_SERVER` cap prevents any single server from being flooded.
- **🧹 Self-cleaning** — idle flows are released after a timeout, so capacity is reclaimed from disconnected clients automatically.
- **🌍 Multi-region by design** — each region runs its own isolated balancer, port, and health checker in the same process.
- **🔍 Transparent to OpenVPN** — no changes needed on your servers; the balancer just relays raw UDP datagrams.

---

## ⚙️ How It Works

### Architecture

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

### Core components

**1. `LoadBalancer` — the brain**
Keeps all the state for one region: the server list, per-server client counts (`server_usage`), health flags (`server_health`), the round-robin pointer, a `client → server` assignment map, and a `flow_map` recording the last activity timestamp of every `(client_ip, client_port, server_ip, server_port)` flow.

**2. `ClientProtocol` — the front door**
An `asyncio.DatagramProtocol` bound to the region's public port (e.g. `0.0.0.0:1194`). When a packet arrives from a client:
1. If the client is already assigned to a server, reuse that assignment (**stickiness**).
2. Otherwise, pick the next server via **round-robin**, skipping servers that are unhealthy or at capacity.
3. Record/refresh the flow's activity timestamp.
4. Forward the datagram to the chosen server through its `ServerProtocol`.

**3. `ServerProtocol` — the back door**
One persistent UDP socket per upstream server. When the server replies, the packet is matched against `flow_map` to find which client it belongs to, and it's sent back to that client from the original listening socket — so from the client's perspective, all traffic comes from the one address it connected to.

**4. Health check task**
Every `HEALTHCHECK_INTERVAL` seconds, each server is pinged asynchronously (ICMP). A failed ping marks the server **UNHEALTHY**: new clients are steered away from it, but existing flows are left alone until they idle out. Once the server responds again, it is marked **HEALTHY** and rejoins the rotation.

**5. Idle-flow reaper**
The main loop wakes every 5 seconds and scans `flow_map`. Any flow silent for longer than `IDLE_TIMEOUT_SECONDS` is released: its record is deleted, the server's usage counter is decremented, and the client-to-server mapping is removed — freeing that slot for a new client.

### Packet lifecycle (end to end)

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

- The health check uses **ICMP ping**, so networks that block ICMP need a different probe (e.g., a UDP probe to the OpenVPN port).
- The `ping -c/-W` flags are **Linux-style**; on Windows, adapt them to `-n`/`-w`.
- The sample IPs in the source are **placeholders** — replace them with your real servers before running.
- This balances at the **UDP datagram level**; it does not inspect or terminate the OpenVPN protocol itself.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

## 🤝 Contributing

Contributions are welcome! Feel free to open an issue or submit a pull request for weighted balancing, better health probes, config file support, or Windows compatibility.
