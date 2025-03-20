"""
Advanced position-based rewards for precise 3D control of humanoid body parts.
"""

import numpy as np
from humenv import rewards as humenv_rewards
from dm_control.utils import rewards
import mujoco
from typing import Optional, Dict
import dataclasses
from humenv.rewards import get_chest_upright

@dataclasses.dataclass
class PositionTarget:
    """Target configuration for a body part."""
    x: Optional[float] = None  # None means this axis is ignored
    y: Optional[float] = None
    z: Optional[float] = None
    weight: float = 1.0
    margin: float = 0.2
    sigmoid: str = "linear"  # Added sigmoid parameter for customizing reward shape

@dataclasses.dataclass
class PositionReward(humenv_rewards.RewardFunction):
    """
    Reward for controlling multiple body parts' positions.
    Supports selective axis control with individual weights.
    """
    targets: Dict[str, PositionTarget]  # body_name -> target
    upright_weight: float = 0.3
    control_weight: float = 0.2

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        # Position rewards
        position_rewards = []
        total_weight = sum(target.weight for target in self.targets.values())

        for body_name, target in self.targets.items():
            current_pos = data.xpos[model.body(body_name).id].copy()
            axis_rewards = []

            # Check each axis - refactored to reduce duplication
            for i, (axis_val, target_val) in enumerate([
                (current_pos[0], target.x),
                (current_pos[1], target.y),
                (current_pos[2], target.z)
            ]):
                if target_val is not None:
                    reward = rewards.tolerance(
                        abs(axis_val - target_val),
                        bounds=(0, target.margin),
                        margin=target.margin,
                        value_at_margin=0.01,
                        sigmoid=target.sigmoid
                    )
                    # Handle both tensor and float return types
                    reward = reward.item() if hasattr(reward, 'item') else float(reward)
                    axis_rewards.append(reward)

            if axis_rewards:
                # Multiplicative combination of axis rewards
                body_reward = np.prod(axis_rewards)
                weighted_reward = np.power(body_reward, target.weight / total_weight)
                position_rewards.append(weighted_reward)

        # Multiplicative combination of body part rewards
        position_reward = np.prod(position_rewards) if position_rewards else 0.0
        
        # Get upright reward
        upright_reward = get_chest_upright(model, data)
        upright_reward = upright_reward.item() if hasattr(upright_reward, 'item') else float(upright_reward)
        
        # Compute control cost (penalize large actions)
        ctrl = data.ctrl.copy()
        control_reward = rewards.tolerance(
            np.linalg.norm(ctrl),
            bounds=(0, 1),
            margin=1,
            value_at_margin=0,
            sigmoid="quadratic"
        )
        control_reward = control_reward.item() if hasattr(control_reward, 'item') else float(control_reward)
        
        # Combine rewards with weights
        final_reward = (
            (1 - self.upright_weight - self.control_weight) * position_reward +
            self.upright_weight * upright_reward +
            self.control_weight * control_reward
        )
        
        return float(final_reward)

    @staticmethod
    def reward_from_name(name: str) -> Optional["humenv_rewards.RewardFunction"]:
        """
        Parse reward configuration from name string.
        Format: position-{body1}-x{val}-y{val}-z{val}-w{val}-m{val}-s{sigmoid}_{body2}...
        Example: position-Head-x1.5-z1.7-w1.0-m0.3-slinear_L_Hand-x0.5-y0.3-z1.2-w0.8
        """
        if not name.startswith("position-"):
            return None

        try:
            targets = {}
            parts = name[9:].split("_")  # Remove "position-" prefix
            
            for part in parts:
                configs = part.split("-")
                if len(configs) < 2:
                    print(f"Warning: Invalid body part config: {part}")
                    continue
                    
                body_name = configs[0]
                target = PositionTarget()
                
                for config in configs[1:]:
                    if not config:
                        continue
                    if config.startswith("x"):
                        target.x = float(config[1:])
                    elif config.startswith("y"):
                        target.y = float(config[1:])
                    elif config.startswith("z"):
                        target.z = float(config[1:])
                    elif config.startswith("w"):
                        target.weight = float(config[1:])
                    elif config.startswith("m"):
                        target.margin = float(config[1:])
                    elif config.startswith("s"):
                        target.sigmoid = config[1:]
                
                targets[body_name] = target

            # Validate that we have at least one target
            if not targets:
                print(f"Warning: No valid targets found in: {name}")
                return None
                
            return PositionReward(targets=targets)

        except (ValueError, IndexError) as e:
            print(f"Warning: Invalid position reward format: {name}")
            print(f"Error: {e}")
            return None

    @staticmethod
    def create(targets: Dict[str, PositionTarget]) -> "PositionReward":
        """
        Create a position reward directly with a dictionary of targets.
        
        Example:
        reward = PositionReward.create({
            "Head": PositionTarget(z=1.7, weight=1.0),
            "L_Hand": PositionTarget(x=0.5, y=0.3, z=1.2, weight=0.8)
        })
        """
        return PositionReward(targets=targets)

    @staticmethod
    def print_usage():
        """Print usage instructions."""
        print("\nPositionReward Usage:")
        print("\nMethod 1 - String format:")
        print("position-{body}-x{val}-y{val}-z{val}-w{val}-m{margin}-s{sigmoid}_{body2}...")
        print("Example: position-Head-x1.5-z1.7-w1.0-m0.3-slinear_L_Hand-x0.5-y0.3-z1.2-w0.8")
        
        print("\nMethod 2 - Direct creation:")
        print("""
reward = PositionReward.create({
    "Head": PositionTarget(z=1.7, weight=1.0),
    "L_Hand": PositionTarget(x=0.5, y=0.3, z=1.2, weight=0.8)
})
        """)
        
        print("\nAvailable body parts:")
        print("- Head, Pelvis")
        print("- L_Hand, R_Hand")
        print("- L_Toe, R_Toe")
        print("- Torso, Chest")
        
        print("\nParameters:")
        print("- x, y, z: target positions (optional)")
        print("- weight: importance (default: 1.0)")
        print("- margin: tolerance (default: 0.2)")
        print("- sigmoid: reward shape ('linear', 'quadratic', etc.) (default: 'linear')") 