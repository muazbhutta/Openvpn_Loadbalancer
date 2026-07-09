#!/usr/bin/env python3

import asyncio
import socket
import time
import logging
import subprocess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

MAX_CLIENTS_PER_SERVER = 100
IDLE_TIMEOUT_SECONDS = 300
HEALTHCHECK_INTERVAL = 15
HEALTHCHECK_TIMEOUT = 3

USA_SERVERS = [
    ("102.123.112.2", 1194),
    ("1.1.1.1", 1194),
    ("2.2.2.2", 1194),
]

UK_SERVERS = [
    ("192.180.231.1", 1194),
    ("9.2.41.5", 1194),
    ("192.179.24.5", 1194),
]

SINGAPORE_SERVERS = [
    ("12.12.12.12", 1194),
    ("13.13.13.13", 1194),
    ("14.14.14.14", 1194),
]

GERMANY_SERVERS = [
    ("183.23.54.2", 1194),
    ("183.24.12.1", 1194),
    ("10.234.22.4", 1194),
]


async def check_server_health(ip, port):
    cmd = ["ping", "-c", "1", "-W", str(HEALTHCHECK_TIMEOUT), ip]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
        return (proc.returncode == 0)
    except Exception:
        return False


class LoadBalancer:

    def __init__(self, servers):
        self.servers = servers
        self.num_servers = len(servers)
        self.server_usage = [0] * self.num_servers
        self.server_health = [True] * self.num_servers
        self.server_index = 0
        self.client_to_server_index = {}
        self.flow_map = {}

    def pick_server_round_robin(self):
        for i in range(self.num_servers):
            idx = (self.server_index + i) % self.num_servers
            if self.server_health[idx] and (self.server_usage[idx] < MAX_CLIENTS_PER_SERVER):
                self.server_index = (idx + 1) % self.num_servers
                return idx

        return None

    def assign_server(self, client_addr):
        if client_addr in self.client_to_server_index:
            return self.client_to_server_index[client_addr]

        idx = self.pick_server_round_robin()
        if idx is None:
            return None

        self.server_usage[idx] += 1
        self.client_to_server_index[client_addr] = idx
        logging.info(
            f"Assigned client {client_addr} to server {self.servers[idx]} "
            f"(usage={self.server_usage[idx]}/{MAX_CLIENTS_PER_SERVER}, healthy={self.server_health[idx]})"
        )
        return idx

    def add_flow(self, client_addr, server_addr):
        flow_key = (client_addr[0], client_addr[1], server_addr[0], server_addr[1])
        self.flow_map[flow_key] = time.time()

    def update_flow_activity(self, client_addr, server_addr):
        flow_key = (client_addr[0], client_addr[1], server_addr[0], server_addr[1])
        if flow_key in self.flow_map:
            self.flow_map[flow_key] = time.time()

    def release_flow(self, flow_key):
        if flow_key not in self.flow_map:
            return

        del self.flow_map[flow_key]

        (c_ip, c_port, s_ip, s_port) = flow_key
        client_addr = (c_ip, c_port)

        if client_addr in self.client_to_server_index:
            idx = self.client_to_server_index[client_addr]
            assigned_ip, assigned_port = self.servers[idx]

            if assigned_ip == s_ip and assigned_port == s_port:
                self.server_usage[idx] = max(0, self.server_usage[idx] - 1)

            del self.client_to_server_index[client_addr]

            logging.info(
                f"Released flow {flow_key}. Usage on server index {idx} = {self.server_usage[idx]}"
            )

    def check_idle_timeouts(self):
        now = time.time()
        to_release = []
        for key, last_ts in self.flow_map.items():
            if (now - last_ts) > IDLE_TIMEOUT_SECONDS:
                to_release.append(key)

        for flow_key in to_release:
            logging.info(f"Idle timeout for flow {flow_key}; releasing.")
            self.release_flow(flow_key)

    def set_server_health(self, idx, healthy):
        if self.server_health[idx] != healthy:
            self.server_health[idx] = healthy
            status_str = "HEALTHY" if healthy else "UNHEALTHY"
            logging.info(f"Server {self.servers[idx]} marked as {status_str}.")

    def get_server_by_index(self, idx):
        return self.servers[idx]


class ServerProtocol(asyncio.DatagramProtocol):

    def __init__(self, load_balancer, server_idx, client_protocol):
        self.lb = load_balancer
        self.server_idx = server_idx
        self.client_protocol = client_protocol
        self.transport = None

        self.server_ip, self.server_port = self.lb.get_server_by_index(self.server_idx)

    def connection_made(self, transport):
        self.transport = transport
        local_addr = transport.get_extra_info('sockname')
        logging.info(
            f"[ServerProtocol] Connected to upstream {self.server_ip}:{self.server_port}, local socket {local_addr}"
        )

    def datagram_received(self, data, remote_addr):
        self.client_protocol.handle_server_packet(data, remote_addr)

    def sendto_server(self, data):
        if not self.transport:
            logging.error(f"[ServerProtocol] No transport for {self.server_ip}:{self.server_port}")
            return
        self.transport.sendto(data, (self.server_ip, self.server_port))


class ClientProtocol(asyncio.DatagramProtocol):

    def __init__(self, load_balancer):
        self.lb = load_balancer
        self.transport = None
        self.server_protocols = [None] * self.lb.num_servers

    def connection_made(self, transport):
        self.transport = transport
        local_addr = transport.get_extra_info('sockname')
        logging.info(f"[ClientProtocol] Listening on {local_addr}")

    def datagram_received(self, data, client_addr):
        idx = self.lb.assign_server(client_addr)
        if idx is None:
            logging.warning(f"No healthy/available server for client {client_addr}; dropping.")
            return

        server_ip, server_port = self.lb.get_server_by_index(idx)

        self.lb.add_flow(client_addr, (server_ip, server_port))
        self.lb.update_flow_activity(client_addr, (server_ip, server_port))

        server_proto = self.server_protocols[idx]
        if server_proto:
            server_proto.sendto_server(data)
        else:
            logging.error(f"[ClientProtocol] Missing server_proto idx={idx}; cannot forward data.")

    def handle_server_packet(self, data, actual_server_addr):
        matches = []
        now = time.time()
        for (c_ip, c_port, s_ip, s_port), last_ts in self.lb.flow_map.items():
            if s_ip == actual_server_addr[0] and s_port == actual_server_addr[1]:
                matches.append((c_ip, c_port, s_ip, s_port))

        if not matches:
            logging.warning(f"[ClientProtocol] Unknown flow from {actual_server_addr}; dropping packet.")
            return

        for flow_key in matches:
            self.lb.flow_map[flow_key] = now
            c_ip, c_port, _, _ = flow_key
            client_address = (c_ip, c_port)
            self.transport.sendto(data, client_address)

    def connection_lost(self, exc):
        logging.error(f"[ClientProtocol] Connection lost: {exc}")


async def create_region_services(loop, servers, listen_port):
    lb = LoadBalancer(servers)

    client_transport, client_protocol = await loop.create_datagram_endpoint(
        lambda: ClientProtocol(lb),
        local_addr=('0.0.0.0', listen_port)
    )

    for i, (srv_ip, srv_port) in enumerate(servers):
        def server_factory():
            return ServerProtocol(lb, i, client_protocol)

        server_transport, server_proto = await loop.create_datagram_endpoint(
            server_factory,
            remote_addr=(srv_ip, srv_port)
        )
        client_protocol.server_protocols[i] = server_proto

        local_socket = server_transport.get_extra_info('sockname')
        logging.info(f"[create_region_services] region port={listen_port}, server {srv_ip}:{srv_port}, local={local_socket}")

    return lb, client_transport, client_protocol


async def healthcheck_task(lb):
    while True:
        for idx, (ip, port) in enumerate(lb.servers):
            healthy = await check_server_health(ip, port)
            lb.set_server_health(idx, healthy)

        await asyncio.sleep(HEALTHCHECK_INTERVAL)


async def main():
    loop = asyncio.get_running_loop()

    usa_lb, usa_transport, usa_protocol = await create_region_services(loop, USA_SERVERS, 1194)
    logging.info("USA region load balancer running on port 1194...")

    uk_lb, uk_transport, uk_protocol = await create_region_services(loop, UK_SERVERS, 1195)
    logging.info("UK region load balancer running on port 1195...")

    sg_lb, sg_transport, sg_protocol = await create_region_services(loop, SINGAPORE_SERVERS, 1196)
    logging.info("Singapore region load balancer running on port 1196...")

    de_lb, de_transport, de_protocol = await create_region_services(loop, GERMANY_SERVERS, 1197)
    logging.info("Germany region load balancer running on port 1197...")

    asyncio.create_task(healthcheck_task(usa_lb))
    asyncio.create_task(healthcheck_task(uk_lb))
    asyncio.create_task(healthcheck_task(sg_lb))
    asyncio.create_task(healthcheck_task(de_lb))

    try:
        while True:
            usa_lb.check_idle_timeouts()
            uk_lb.check_idle_timeouts()
            sg_lb.check_idle_timeouts()
            de_lb.check_idle_timeouts()
            await asyncio.sleep(5.0)
    except KeyboardInterrupt:
        logging.info("Shutting down load balancer...")
    finally:
        usa_transport.close()
        uk_transport.close()
        sg_transport.close()
        de_transport.close()


if __name__ == '__main__':
    asyncio.run(main())
