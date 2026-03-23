export interface ChannelQueueStatus {
  inbound_size: number;
  outbound_size: number;
}

export interface ZMQSocketInfo {
  type: string;
  address: string;
  connected: boolean;
}

export interface ZMQQueueStatus {
  is_initialized: boolean;
  bind_addr: string;
  pub_socket: ZMQSocketInfo | null;
  router_socket: ZMQSocketInfo | null;
  sub_sockets: Array<{
    agent_id: string;
    bot_id: string;
    topics: string[];
    address: string;
    connected: boolean;
  }>;
  pending_delegations: number;
}

export interface QueueStatus {
  bot_id: string;
  channel_queue: ChannelQueueStatus;
  zmq_queue: ZMQQueueStatus;
  last_updated: string;
  error?: string;
}
