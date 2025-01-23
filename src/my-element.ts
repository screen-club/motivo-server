import { LitElement, css, html } from 'lit'
import { customElement, property, state } from 'lit/decorators.js'
import './components/reward-config';
import { RewardConfig } from './types/rewards';
import {
  getMoveReward,
  getJumpReward,
  getRotationReward,
  getMoveAndRaiseArmsReward
} from './rewards';

@customElement('my-element')
export class MyElement extends LitElement {
  @state()
  private ws: WebSocket | null = null;

  @state()
  private lastReward: number = 0;

  @state()
  private connected: boolean = false;

  @property({ type: Number })
  count = 0;

  @state()
  private customPrompt: string = '';

  @state()
  private isGenerating: boolean = false;

  @state()
  private currentConfig: RewardConfig = {
    rewards: [{
      name: 'move-ego',
      move_speed: 2.0,
      stand_height: 1.4,
      move_angle: 0,
      egocentric_target: true,
      low_height: 0.6,
      stay_low: false
    }],
    weights: [1.0]
  };

  @state()
  private combinationType: 'additive' | 'multiplicative' | 'geometric' | 'min' | 'max' = 'additive';

  connectedCallback() {
    super.connectedCallback();
    this.connectWebSocket();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this.ws) {
      this.ws.close();
    }
  }

  private connectWebSocket() {
    this.ws = new WebSocket('ws://localhost:8765');
    
    this.ws.onopen = () => {
      this.connected = true;
      console.log('WebSocket Connected');
    };

    this.ws.onclose = () => {
      this.connected = false;
      console.log('WebSocket Disconnected');
      // Attempt to reconnect after 5 seconds
      setTimeout(() => this.connectWebSocket(), 5000);
    };

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'reward') {
        this.lastReward = data.value;
        this.requestUpdate();
      }
    };
  }

  private _requestReward(config: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'request_reward',
        reward: config,
        combination_type: this.combinationType,
        timestamp: new Date().toISOString()
      }));
    }
  }

  // Reward request methods
  private _requestMove() {
    this._requestReward(getMoveReward());
  }

  private _requestMoveLow() {
    this._requestReward(getMoveReward(true));
  }

  private _requestJump() {
    this._requestReward(getJumpReward());
  }

  private _requestRotation() {
    this._requestReward(getRotationReward());
  }

  private _requestHeadstand() {
    this._requestReward({
      rewards: [
        { name: 'headstand', stand_pelvis_height: 0.95 }
      ],
      weights: [1.0]
    });
  }

  private _requestCrawl() {
    this._requestReward({
      rewards: [
        { 
          name: 'crawl', 
          spine_height: 0.4, 
          move_speed: 2.0, 
          direction: 1  // 1 for up, -1 for down
        }
      ],
      weights: [1.0]
    });
  }

  private _requestLieDown() {
    this._requestReward({
      rewards: [
        { name: 'liedown', direction: 'up' }  // can be 'up' or 'down'
      ],
      weights: [1.0]
    });
  }

  private _requestSit() {
    this._requestReward({
      rewards: [
        { 
          name: 'sit', 
          pelvis_height_th: 0,
          constrained_knees: true
        }
      ],
      weights: [1.0]
    });
  }

  private _requestSplit() {
    this._requestReward({
      rewards: [
        { name: 'split', distance: 1.5 }
      ],
      weights: [1.0]
    });
  }

  private _requestRaiseArms() {
    this._requestReward({
      rewards: [
        { 
          name: 'raisearms',
          left: 'h',  // 'l' for low, 'm' for middle, 'h' for high
          right: 'h'
        }
      ],
      weights: [1.0]
    });
  }

  private _requestMoveAndRaiseArms() {
    this._requestReward(getMoveAndRaiseArmsReward({
      leftPose: 'h',
      rightPose: 'h',
      moveSpeed: 2.0,
      moveAngle: 0,
      standHeight: 1.4,
      egocentricTarget: true
    }));
  }

  private _requestMoveAndRaiseLeftArm() {
    this._requestReward(getMoveAndRaiseArmsReward({
      leftPose: 'h',
      rightPose: 'l',
      moveSpeed: 2.0,
      moveAngle: 0,
      standHeight: 1.4,
      egocentricTarget: true,
      armCoeff: 1.0
    }));
  }

  private _requestMoveAndRaiseRightArm() {
    this._requestReward(getMoveAndRaiseArmsReward({
      leftPose: 'l',
      rightPose: 'h',
      moveSpeed: 2.0,
      moveAngle: 0,
      standHeight: 1.4,
      egocentricTarget: true,
      armCoeff: 1.0
    }));
  }

  private async _generateCustomReward() {
    if (!this.customPrompt.trim()) return;
    
    this.isGenerating = true;
    try {
      const response = await fetch('http://localhost:5002/generate-reward', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ prompt: this.customPrompt }),
      });
      
      const data = await response.json();
      if (data.error) {
        console.error('Error:', data.error);
        return;
      }
      
      // Parse the reward configuration from Claude's response
      try {
        const rewardConfig = JSON.parse(data.reward_config);
        console.log(rewardConfig);
        this._requestReward(rewardConfig);
      } catch (e) {
        console.error('Failed to parse reward config:', e);
      }
    } catch (e) {
      console.error('Failed to generate reward:', e);
    } finally {
      this.isGenerating = false;
    }
  }

  private _handleConfigChange(e: CustomEvent<RewardConfig>) {
    this.currentConfig = e.detail;
  }

  private _handleConfigSend(e: CustomEvent<RewardConfig>) {
    this._requestReward(e.detail);
  }

  private _cleanRewards() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'clean_rewards',
        timestamp: new Date().toISOString()
      }));
    }
  }

  render() {
    return html`
      <div class="container">
        <h1>Liminal AI test</h1>
        
        <div class="status ${this.connected ? 'connected' : 'disconnected'}">
          WebSocket: ${this.connected ? 'Connected' : 'Disconnected'}
        </div>

        <div class="card">
          <div class="combination-type">
            <label for="combination-type">Global Reward Combination:</label>
            <select 
              id="combination-type"
              .value=${this.combinationType}
              @change=${(e: Event) => {
                const select = e.target as HTMLSelectElement;
                this.combinationType = select.value as typeof this.combinationType;
              }}
              ?disabled=${!this.connected}
            >
              <option value="additive">Additive (Default)</option>
              <option value="multiplicative">Multiplicative</option>
              <option value="geometric">Geometric Mean</option>
              <option value="min">Minimum (Bottleneck)</option>
              <option value="max">Maximum (Optimistic)</option>
            </select>
          </div>

          <button
            @click=${this._cleanRewards}
            ?disabled=${!this.connected}
          >
            Reset Rewards
          </button>

          <div class="custom-prompt">
            <input
              type="text"
              placeholder="Enter custom prompt..."
              .value=${this.customPrompt}
              @input=${(e: InputEvent) => this.customPrompt = (e.target as HTMLInputElement).value}
              ?disabled=${!this.connected || this.isGenerating}
            >
            <button
              @click=${this._generateCustomReward}
              ?disabled=${!this.connected || this.isGenerating || !this.customPrompt.trim()}
            >
              ${this.isGenerating ? 'Generating...' : 'Generate'}
            </button>
          </div>

          <reward-config
            .config=${this.currentConfig}
            ?disabled=${!this.connected}
            @config-change=${this._handleConfigChange}
            @send-config=${this._handleConfigSend}
          ></reward-config>

          <div class="reward">
            Last Reward: ${this.lastReward.toFixed(4)}
          </div>
        </div>
      </div>
    `;
  }

}

declare global {
  interface HTMLElementTagNameMap {
    'my-element': MyElement
  }
}
