import { RewardConfig } from '../types/rewards';

export function getJumpReward(): RewardConfig {
  return {
    rewards: [
      { name: 'jump', jump_height: 2.0, max_velocity: 5.0 }
    ],
    weights: [1.0]
  };
} 