import { RewardConfig } from '../types/rewards';

type ArmPose = 'l' | 'm' | 'h';  // low, middle, high

interface RaiseArmsOptions {
  left?: ArmPose;
  right?: ArmPose;
}

export function getRaiseArmsReward(options: RaiseArmsOptions = {}): RewardConfig {
  const {
    left = 'h',
    right = 'h'
  } = options;

  return {
    rewards: [
      {
        name: 'raisearms',
        left,
        right
      }
    ],
    weights: [1.0]
  };
} 