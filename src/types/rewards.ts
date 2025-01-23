export interface BaseReward {
  name: string;
  weight?: number;
}

export interface MoveEgoReward extends BaseReward {
  name: 'move-ego';
  move_speed?: number;
  stand_height?: number;
  move_angle?: number;
  egocentric_target?: boolean;
  low_height?: number;
  stay_low?: boolean;
}

export interface JumpReward extends BaseReward {
  name: 'jump';
  jump_height?: number;
  max_velocity?: number;
}

export interface RotationReward extends BaseReward {
  name: 'rotation';
  axis?: 'x' | 'y' | 'z';
  target_ang_velocity?: number;
  stand_pelvis_height?: number;
}

export interface HeadstandReward extends BaseReward {
  name: 'headstand';
  stand_pelvis_height?: number;
}

export interface CrawlReward extends BaseReward {
  name: 'crawl';
  spine_height?: number;
  move_speed?: number;
  direction?: 'u' | 'd';
}

export interface LieDownReward extends BaseReward {
  name: 'liedown';
  direction?: 'up' | 'down';
}

export interface SitReward extends BaseReward {
  name: 'sit';
  pelvis_height_th?: number;
  constrained_knees?: boolean;
}

export interface SplitReward extends BaseReward {
  name: 'split';
  distance?: number;
}

export interface RaiseArmsReward extends BaseReward {
  name: 'raisearms';
  left?: 'l' | 'm' | 'h';
  right?: 'l' | 'm' | 'h';
}

export interface MoveAndRaiseArmsReward extends BaseReward {
  name: 'move-and-raise-arms';
  move_speed?: number;
  move_angle?: number;
  left_pose?: 'l' | 'm' | 'h';
  right_pose?: 'l' | 'm' | 'h';
  stand_height?: number;
  egocentric_target?: boolean;
  arm_coeff?: number;
  loc_coeff?: number;
}

export type RewardType = 
  | MoveEgoReward
  | JumpReward
  | RotationReward
  | HeadstandReward
  | CrawlReward
  | LieDownReward
  | SitReward
  | SplitReward
  | RaiseArmsReward
  | MoveAndRaiseArmsReward;

export interface RewardConfig {
  rewards: RewardType[];
  weights?: number[];
} 