import { RewardConfig } from '../types/rewards';

type ArmPose = 'l' | 'm' | 'h';

interface MoveAndRaiseArmsOptions {
  leftPose?: ArmPose;
  rightPose?: ArmPose;
  moveSpeed?: number;
  moveAngle?: number;
  standHeight?: number;
  lowHeight?: number;
  stayLow?: boolean;
  egocentricTarget?: boolean;
  armCoeff?: number;
  visualizeTargetAngle?: boolean;
  // Note: loc_coeff is computed internally based on arm positions
}

export function getMoveAndRaiseArmsReward(options: MoveAndRaiseArmsOptions = {}): RewardConfig {
  const {
    leftPose = 'h',
    rightPose = 'h',
    moveSpeed = 2.0,
    moveAngle = 0,
    standHeight = 1.4,
    lowHeight = 0.6,
    stayLow = false,
    egocentricTarget = true,
    armCoeff = 1.0,
    visualizeTargetAngle = true
  } = options;

  return {
    rewards: [
      {
        name: 'move-and-raise-arms',
        move_speed: moveSpeed,
        move_angle: moveAngle,
        left_pose: leftPose,
        right_pose: rightPose,
        stand_height: standHeight,
        low_height: lowHeight,
        stay_low: stayLow,
        egocentric_target: egocentricTarget,
        arm_coeff: armCoeff,
        visualize_target_angle: visualizeTargetAngle
        // loc_coeff is computed internally in Python
      }
    ],
    weights: [1.0]
  };
} 