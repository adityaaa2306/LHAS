/**
 * eventBridge - Real-time event subscription service
 * Connects frontend to backend claim extraction event pipeline
 */

class EventBridge {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 3000;
  private listeners: Map<string, Set<(data: any) => void>> = new Map();
  private isConnecting = false;

  constructor(url: string = `ws://${window.location.hostname}:8000/ws/events`) {
    this.url = url;
  }

  /**
   * Connect to the WebSocket event stream
   */
  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.isConnecting) return;

      this.isConnecting = true;

      try {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
          console.log('[EventBridge] Connected');
          this.reconnectAttempts = 0;
          this.isConnecting = false;
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            this.emit(message.event_type, message.data);
          } catch (error) {
            console.error('[EventBridge] Failed to parse message:', error);
          }
        };

        this.ws.onerror = (error) => {
          console.error('[EventBridge] Connection error:', error);
          this.isConnecting = false;
          reject(error);
        };

        this.ws.onclose = () => {
          console.log('[EventBridge] Disconnected');
          this.isConnecting = false;
          this.attemptReconnect();
        };
      } catch (error) {
        this.isConnecting = false;
        reject(error);
      }
    });
  }

  /**
   * Subscribe to an event type
   */
  on(eventType: string, callback: (data: any) => void): () => void {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }

    this.listeners.get(eventType)!.add(callback);

    // Return unsubscribe function
    return () => {
      this.listeners.get(eventType)?.delete(callback);
    };
  }

  /**
   * Emit event to all listeners
   */
  private emit(eventType: string, data: any) {
    const handlers = this.listeners.get(eventType);
    if (handlers) {
      handlers.forEach((handler) => {
        try {
          handler(data);
        } catch (error) {
          console.error(`[EventBridge] Error in ${eventType} handler:`, error);
        }
      });
    }

    // Also dispatch browser event for legacy support
    window.dispatchEvent(new CustomEvent(`claims:${eventType}`, { detail: data }));
  }

  /**
   * Attempt to reconnect
   */
  private attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[EventBridge] Max reconnection attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * this.reconnectAttempts;
    console.log(`[EventBridge] Attempting reconnect in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

    setTimeout(() => {
      this.connect().catch((error) => {
        console.error('[EventBridge] Reconnection failed:', error);
      });
    }, delay);
  }

  /**
   * Disconnect from event stream
   */
  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.listeners.clear();
  }

  /**
   * Check if connected
   */
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// Singleton instance
let eventBridgeInstance: EventBridge | null = null;

export const getEventBridge = (): EventBridge => {
  if (!eventBridgeInstance) {
    eventBridgeInstance = new EventBridge();
  }
  return eventBridgeInstance;
};

export const initializeEventBridge = async (): Promise<void> => {
  const bridge = getEventBridge();
  try {
    await bridge.connect();
  } catch (error) {
    console.warn('[EventBridge] Failed to initialize event connection, continuing without real-time events:', error);
  }
};
