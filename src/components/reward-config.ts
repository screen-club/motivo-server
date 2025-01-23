import { LitElement, css, html } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { RewardConfig, RewardType } from '../types/rewards';

@customElement('reward-config')
export class RewardConfigElement extends LitElement {
  @property({ type: Object })
  config: RewardConfig = { rewards: [], weights: [] };

  @property({ type: Boolean })
  disabled = false;

  private _updateReward(index: number, updates: Partial<RewardType>) {
    const newConfig = {
      ...this.config,
      rewards: [...this.config.rewards],
      weights: [...(this.config.weights || [])]
    };
    newConfig.rewards[index] = { ...newConfig.rewards[index], ...updates };
    this.dispatchEvent(new CustomEvent('config-change', { detail: newConfig }));
  }

  private _removeReward(index: number) {
    const newConfig = {
      ...this.config,
      rewards: this.config.rewards.filter((_, i) => i !== index),
      weights: (this.config.weights || []).filter((_, i) => i !== index)
    };
    this.dispatchEvent(new CustomEvent('config-change', { detail: newConfig }));
  }

  private _updateWeight(index: number, weight: number) {
    const newConfig = {
      ...this.config,
      weights: [...(this.config.weights || [])]
    };
    newConfig.weights[index] = weight;
    this.dispatchEvent(new CustomEvent('config-change', { detail: newConfig }));
  }

  private _renderMoveEgoConfig(reward: any, index: number) {
    return html`
      <div class="reward-config">
        <div class="reward-header">
          <h3>Move Configuration</h3>
          <button @click=${() => this._removeReward(index)} ?disabled=${this.disabled}>Remove</button>
        </div>
        <div class="form-group">
          <label>
            Weight:
            <input type="number" step="0.1"
              .value=${this.config.weights?.[index] || 1.0}
              @input=${(e: Event) => this._updateWeight(index, Number((e.target as HTMLInputElement).value))}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Move Speed:
            <input type="number" step="0.1"
              .value=${reward.move_speed || 2.0}
              @input=${(e: Event) => this._updateReward(index, { 
                move_speed: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Stand Height:
            <input type="number" step="0.1"
              .value=${reward.stand_height || 1.4}
              @input=${(e: Event) => this._updateReward(index, {
                stand_height: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Move Angle:
            <input type="number"
              .value=${reward.move_angle || 0}
              @input=${(e: Event) => this._updateReward(index, {
                move_angle: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Low Height:
            <input type="number" step="0.1"
              .value=${reward.low_height || 0.6}
              @input=${(e: Event) => this._updateReward(index, {
                low_height: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Stay Low:
            <input type="checkbox"
              .checked=${reward.stay_low || false}
              @change=${(e: Event) => this._updateReward(index, {
                stay_low: (e.target as HTMLInputElement).checked
              })}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Egocentric Target:
            <input type="checkbox"
              .checked=${reward.egocentric_target || true}
              @change=${(e: Event) => this._updateReward(index, {
                egocentric_target: (e.target as HTMLInputElement).checked
              })}
              ?disabled=${this.disabled}
            >
          </label>
        </div>
      </div>
    `;
  }

  private _renderJumpConfig(reward: any, index: number) {
    return html`
      <div class="reward-config">
        <div class="reward-header">
          <h3>Jump Configuration</h3>
          <button @click=${() => this._removeReward(index)} ?disabled=${this.disabled}>Remove</button>
        </div>
        <div class="form-group">
          <label>
            Weight:
            <input type="number" step="0.1"
              .value=${this.config.weights?.[index] || 1.0}
              @input=${(e: Event) => this._updateWeight(index, Number((e.target as HTMLInputElement).value))}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Jump Height:
            <input type="number" step="0.1"
              .value=${reward.jump_height || 2.0}
              @input=${(e: Event) => this._updateReward(index, {
                jump_height: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Max Velocity:
            <input type="number" step="0.1"
              .value=${reward.max_velocity || 5.0}
              @input=${(e: Event) => this._updateReward(index, {
                max_velocity: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
        </div>
      </div>
    `;
  }

  private _renderRotationConfig(reward: any, index: number) {
    return html`
      <div class="reward-config">
        <div class="reward-header">
          <h3>Rotation Configuration</h3>
          <button @click=${() => this._removeReward(index)} ?disabled=${this.disabled}>Remove</button>
        </div>
        <div class="form-group">
          <label>
            Weight:
            <input type="number" step="0.1"
              .value=${this.config.weights?.[index] || 1.0}
              @input=${(e: Event) => this._updateWeight(index, Number((e.target as HTMLInputElement).value))}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Axis:
            <select
              .value=${reward.axis || 'x'}
              @change=${(e: Event) => this._updateReward(index, {
                axis: (e.target as HTMLSelectElement).value
              })}
              ?disabled=${this.disabled}
            >
              <option value="x">X</option>
              <option value="y">Y</option>
              <option value="z">Z</option>
            </select>
          </label>
          <label>
            Target Angular Velocity:
            <input type="number" step="0.1"
              .value=${reward.target_ang_velocity || 5.0}
              @input=${(e: Event) => this._updateReward(index, {
                target_ang_velocity: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Stand Pelvis Height:
            <input type="number" step="0.1"
              .value=${reward.stand_pelvis_height || 0.8}
              @input=${(e: Event) => this._updateReward(index, {
                stand_pelvis_height: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
        </div>
      </div>
    `;
  }

  private _renderHeadstandConfig(reward: any, index: number) {
    return html`
      <div class="reward-config">
        <div class="reward-header">
          <h3>Headstand Configuration</h3>
          <button @click=${() => this._removeReward(index)} ?disabled=${this.disabled}>Remove</button>
        </div>
        <div class="form-group">
          <label>
            Weight:
            <input type="number" step="0.1"
              .value=${this.config.weights?.[index] || 1.0}
              @input=${(e: Event) => this._updateWeight(index, Number((e.target as HTMLInputElement).value))}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Stand Pelvis Height:
            <input type="number" step="0.05"
              .value=${reward.stand_pelvis_height || 0.95}
              @input=${(e: Event) => this._updateReward(index, {
                stand_pelvis_height: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
        </div>
      </div>
    `;
  }

  private _renderCrawlConfig(reward: any, index: number) {
    return html`
      <div class="reward-config">
        <div class="reward-header">
          <h3>Crawl Configuration</h3>
          <button @click=${() => this._removeReward(index)} ?disabled=${this.disabled}>Remove</button>
        </div>
        <div class="form-group">
          <label>
            Weight:
            <input type="number" step="0.1"
              .value=${this.config.weights?.[index] || 1.0}
              @input=${(e: Event) => this._updateWeight(index, Number((e.target as HTMLInputElement).value))}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Spine Height:
            <input type="number" step="0.1"
              .value=${reward.spine_height || 0.4}
              @input=${(e: Event) => this._updateReward(index, {
                spine_height: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Move Speed:
            <input type="number" step="0.1"
              .value=${reward.move_speed || 2.0}
              @input=${(e: Event) => this._updateReward(index, {
                move_speed: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Direction:
            <select
              .value=${reward.direction || 'u'}
              @change=${(e: Event) => this._updateReward(index, {
                direction: (e.target as HTMLSelectElement).value
              })}
              ?disabled=${this.disabled}
            >
              <option value="u">Up</option>
              <option value="d">Down</option>
            </select>
          </label>
        </div>
      </div>
    `;
  }

  private _renderLieDownConfig(reward: any, index: number) {
    return html`
      <div class="reward-config">
        <div class="reward-header">
          <h3>Lie Down Configuration</h3>
          <button @click=${() => this._removeReward(index)} ?disabled=${this.disabled}>Remove</button>
        </div>
        <div class="form-group">
          <label>
            Weight:
            <input type="number" step="0.1"
              .value=${this.config.weights?.[index] || 1.0}
              @input=${(e: Event) => this._updateWeight(index, Number((e.target as HTMLInputElement).value))}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Direction:
            <select
              .value=${reward.direction || 'up'}
              @change=${(e: Event) => this._updateReward(index, {
                direction: (e.target as HTMLSelectElement).value
              })}
              ?disabled=${this.disabled}
            >
              <option value="up">Up</option>
              <option value="down">Down</option>
            </select>
          </label>
        </div>
      </div>
    `;
  }

  private _renderSitConfig(reward: any, index: number) {
    return html`
      <div class="reward-config">
        <div class="reward-header">
          <h3>Sit Configuration</h3>
          <button @click=${() => this._removeReward(index)} ?disabled=${this.disabled}>Remove</button>
        </div>
        <div class="form-group">
          <label>
            Weight:
            <input type="number" step="0.1"
              .value=${this.config.weights?.[index] || 1.0}
              @input=${(e: Event) => this._updateWeight(index, Number((e.target as HTMLInputElement).value))}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Pelvis Height Threshold:
            <input type="number" step="0.1"
              .value=${reward.pelvis_height_th || 0}
              @input=${(e: Event) => this._updateReward(index, {
                pelvis_height_th: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Constrained Knees:
            <input type="checkbox"
              .checked=${reward.constrained_knees || false}
              @change=${(e: Event) => this._updateReward(index, {
                constrained_knees: (e.target as HTMLInputElement).checked
              })}
              ?disabled=${this.disabled}
            >
          </label>
        </div>
      </div>
    `;
  }

  private _renderSplitConfig(reward: any, index: number) {
    return html`
      <div class="reward-config">
        <div class="reward-header">
          <h3>Split Configuration</h3>
          <button @click=${() => this._removeReward(index)} ?disabled=${this.disabled}>Remove</button>
        </div>
        <div class="form-group">
          <label>
            Weight:
            <input type="number" step="0.1"
              .value=${this.config.weights?.[index] || 1.0}
              @input=${(e: Event) => this._updateWeight(index, Number((e.target as HTMLInputElement).value))}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Distance:
            <input type="number" step="0.1"
              .value=${reward.distance || 1.5}
              @input=${(e: Event) => this._updateReward(index, {
                distance: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
        </div>
      </div>
    `;
  }

  private _renderRaiseArmsConfig(reward: any, index: number) {
    return html`
      <div class="reward-config">
        <div class="reward-header">
          <h3>Raise Arms Configuration</h3>
          <button @click=${() => this._removeReward(index)} ?disabled=${this.disabled}>Remove</button>
        </div>
        <div class="form-group">
          <label>
            Weight:
            <input type="number" step="0.1"
              .value=${this.config.weights?.[index] || 1.0}
              @input=${(e: Event) => this._updateWeight(index, Number((e.target as HTMLInputElement).value))}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Left Arm:
            <select
              .value=${reward.left || 'l'}
              @change=${(e: Event) => this._updateReward(index, {
                left: (e.target as HTMLSelectElement).value
              })}
              ?disabled=${this.disabled}
            >
              <option value="l">Low</option>
              <option value="m">Middle</option>
              <option value="h">High</option>
            </select>
          </label>
          <label>
            Right Arm:
            <select
              .value=${reward.right || 'l'}
              @change=${(e: Event) => this._updateReward(index, {
                right: (e.target as HTMLSelectElement).value
              })}
              ?disabled=${this.disabled}
            >
              <option value="l">Low</option>
              <option value="m">Middle</option>
              <option value="h">High</option>
            </select>
          </label>
        </div>
      </div>
    `;
  }

  private _renderMoveAndRaiseArmsConfig(reward: any, index: number) {
    return html`
      <div class="reward-config">
        <div class="reward-header">
          <h3>Move and Raise Arms Configuration</h3>
          <button @click=${() => this._removeReward(index)} ?disabled=${this.disabled}>Remove</button>
        </div>
        <div class="form-group">
          <label>
            Weight:
            <input type="number" step="0.1"
              .value=${this.config.weights?.[index] || 1.0}
              @input=${(e: Event) => this._updateWeight(index, Number((e.target as HTMLInputElement).value))}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Move Speed:
            <input type="number" step="0.1"
              .value=${reward.move_speed || 2.0}
              @input=${(e: Event) => this._updateReward(index, {
                move_speed: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Move Angle:
            <input type="number"
              .value=${reward.move_angle || 0}
              @input=${(e: Event) => this._updateReward(index, {
                move_angle: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Left Pose:
            <select
              .value=${reward.left_pose || 'l'}
              @change=${(e: Event) => this._updateReward(index, {
                left_pose: (e.target as HTMLSelectElement).value
              })}
              ?disabled=${this.disabled}
            >
              <option value="l">Low</option>
              <option value="m">Middle</option>
              <option value="h">High</option>
            </select>
          </label>
          <label>
            Right Pose:
            <select
              .value=${reward.right_pose || 'l'}
              @change=${(e: Event) => this._updateReward(index, {
                right_pose: (e.target as HTMLSelectElement).value
              })}
              ?disabled=${this.disabled}
            >
              <option value="l">Low</option>
              <option value="m">Middle</option>
              <option value="h">High</option>
            </select>
          </label>
          <label>
            Stand Height:
            <input type="number" step="0.1"
              .value=${reward.stand_height || 1.4}
              @input=${(e: Event) => this._updateReward(index, {
                stand_height: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Arm Coefficient:
            <input type="number" step="0.1"
              .value=${reward.arm_coeff || 1.0}
              @input=${(e: Event) => this._updateReward(index, {
                arm_coeff: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Location Coefficient:
            <input type="number" step="0.1"
              .value=${reward.loc_coeff || 1.0}
              @input=${(e: Event) => this._updateReward(index, {
                loc_coeff: Number((e.target as HTMLInputElement).value)
              })}
              ?disabled=${this.disabled}
            >
          </label>
          <label>
            Egocentric Target:
            <input type="checkbox"
              .checked=${reward.egocentric_target || true}
              @change=${(e: Event) => this._updateReward(index, {
                egocentric_target: (e.target as HTMLInputElement).checked
              })}
              ?disabled=${this.disabled}
            >
          </label>
        </div>
      </div>
    `;
  }

  private _sendConfig() {
    this.dispatchEvent(new CustomEvent('send-config', { detail: this.config }));
  }

  private _renderRewardTypeSelector() {
    const rewardTypes = [
      'move-ego',
      'jump',
      'rotation',
      'headstand',
      'crawl',
      'liedown',
      'sit',
      'split',
      'raisearms',
      'move-and-raise-arms'
    ];

    return html`
      <div class="reward-selector">
        <select @change=${this._addRewardType} ?disabled=${this.disabled}>
          <option value="">Add new reward...</option>
          ${rewardTypes.map(type => html`
            <option value=${type}>${type}</option>
          `)}
        </select>
      </div>
    `;
  }

  private _addRewardType(e: Event) {
    const select = e.target as HTMLSelectElement;
    const type = select.value;
    if (!type) return;

    const newReward = { name: type };
    const newConfig = {
      ...this.config,
      rewards: [...this.config.rewards, newReward],
      weights: [...(this.config.weights || []), 1.0]
    };
    this.dispatchEvent(new CustomEvent('config-change', { detail: newConfig }));
    select.value = '';
  }

  render() {
    return html`
      <div class="reward-panel">
        ${this.config.rewards.map((reward, index) => {
          switch(reward.name) {
            case 'move-ego':
              return this._renderMoveEgoConfig(reward, index);
            case 'jump':
              return this._renderJumpConfig(reward, index);
            case 'rotation':
              return this._renderRotationConfig(reward, index);
            case 'headstand':
              return this._renderHeadstandConfig(reward, index);
            case 'crawl':
              return this._renderCrawlConfig(reward, index);
            case 'liedown':
              return this._renderLieDownConfig(reward, index);
            case 'sit':
              return this._renderSitConfig(reward, index);
            case 'split':
              return this._renderSplitConfig(reward, index);
            case 'raisearms':
              return this._renderRaiseArmsConfig(reward, index);
            case 'move-and-raise-arms':
              return this._renderMoveAndRaiseArmsConfig(reward, index);
            default:
              return html`<div>Unsupported reward type: ${reward.name}</div>`;
          }
        })}
        ${this._renderRewardTypeSelector()}
        <div class="actions">
          <button 
            class="send-button"
            @click=${this._sendConfig}
            ?disabled=${this.disabled || this.config.rewards.length === 0}
          >
            Send Configuration
          </button>
        </div>
      </div>
    `;
  }

  static styles = css`
    .reward-panel {
      padding: 1rem;
      border: 1px solid #ccc;
      border-radius: 8px;
    }

    .reward-config {
      margin-bottom: 1rem;
      padding: 1rem;
      border: 1px solid #eee;
      border-radius: 4px;
    }

    .reward-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
    }

    .reward-header h3 {
      margin: 0;
    }

    .form-group {
      display: grid;
      gap: 0.5rem;
    }

    label {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
    }

    input[type="number"], select {
      width: 100px;
      padding: 0.3rem;
    }

    .reward-selector {
      margin-top: 1rem;
    }

    .reward-selector select {
      width: 100%;
      padding: 0.5rem;
    }

    .actions {
      margin-top: 1rem;
      display: flex;
      justify-content: center;
    }

    button {
      padding: 0.3rem 0.6rem;
      border: 1px solid #ccc;
      border-radius: 4px;
      background: white;
      cursor: pointer;
    }

    button:hover:not([disabled]) {
      background: #eee;
    }

    button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .send-button {
      background-color: #4caf50;
      color: white;
      padding: 0.6em 1.2em;
      font-size: 1em;
      border: none;
      border-radius: 4px;
      cursor: pointer;
    }

    .send-button:hover:not([disabled]) {
      background-color: #45a049;
    }

    .send-button:disabled {
      background-color: #cccccc;
      cursor: not-allowed;
    }
  `;
} 