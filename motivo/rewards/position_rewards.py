import numpy as np
from humenv import rewards as humenv_rewards
from dm_control.utils import rewards
import mujoco
from typing import Optional, Dict, Tuple
import dataclasses
from humenv.rewards import get_chest_upright

# Define the transformation functions directly here to avoid complex imports
def get_rotation_matrix_from_pelvis(model, data, name="Pelvis"):
    try:
        body_id = model.body(name).id
        rotation_matrix = data.xmat[body_id].reshape(3, 3).copy()
        return rotation_matrix
    except:
        return np.eye(3)

def transform_point_to_local_frame(point, origin, rotation_matrix):
    translated = point - origin
    local_point = rotation_matrix.T @ translated
    return local_point

BODY_PART_MARGINS = {
    "Head": 0.05,
    "Chest": 0.1,
    "L_Hand": 0.03,
    "R_Hand": 0.03,
    "Pelvis": 0.07,
    "L_Toe": 0.01,
    "R_Toe": 0.01,
}

@dataclasses.dataclass
class PositionTarget:
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    orientation: Optional[np.ndarray] = None
    weight: float = 1.0
    margin: Optional[float] = None
    margin_x: Optional[float] = None
    margin_y: Optional[float] = None
    margin_z: Optional[float] = None
    sigmoid: str = "linear"

@dataclasses.dataclass
class PositionReward(humenv_rewards.RewardFunction):
    targets: Dict[str, PositionTarget]
    upright_weight: float = 0.2
    control_weight: float = 0.2
    orientation_weight: float = 0.2
    use_local_frame: bool = False
    debug: bool = False

    def compute(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        total_position_reward = 0.0
        total_orientation_reward = 0.0
        total_effective_weight = 0.0
        

        pelvis_pos = data.xpos[model.body("Pelvis").id].copy()
        pelvis_rotation = get_rotation_matrix_from_pelvis(model, data) if self.use_local_frame else np.eye(3)

        for body_name, target in self.targets.items():
            try:
                body_id = model.body(body_name).id
                current_pos = data.xpos[body_id].copy()
                current_rot = data.xmat[body_id].reshape(3, 3).copy()

                if self.use_local_frame and body_name == "Pelvis":
                    continue

                if self.use_local_frame:
                    current_pos = transform_point_to_local_frame(current_pos, pelvis_pos, pelvis_rotation)
                    current_rot = pelvis_rotation.T @ current_rot

                margin = target.margin or BODY_PART_MARGINS.get(body_name, 0.05)
                margins = [
                    target.margin_x if target.margin_x is not None else margin,
                    target.margin_y if target.margin_y is not None else margin,
                    target.margin_z if target.margin_z is not None else margin
                ]

                axis_rewards = []
                for i, (axis_val, target_val) in enumerate([
                    (current_pos[0], target.x),
                    (current_pos[1], target.y),
                    (current_pos[2], target.z)
                ]):
                    if target_val is not None:
                        reward = rewards.tolerance(
                            axis_val,
                            bounds=(target_val - margins[i], target_val + margins[i]),
                            margin=margins[i],
                            value_at_margin=0.01,
                            sigmoid=target.sigmoid
                        )
                        #print(f"---")
                        #print("Margin: ", margins[i])
                        #print("Target: ", target_val)
                        #print("sigmoid: ", target.sigmoid)
                        #print("Reward: ", reward)
                        reward = reward.item() if hasattr(reward, 'item') else float(reward)
                        axis_rewards.append(reward)

                if axis_rewards:
                    body_reward = np.mean(axis_rewards)
                    total_position_reward += target.weight * body_reward
                    total_effective_weight += target.weight

                if target.orientation is not None:
                    if target.orientation.shape == (3, 3):
                        dot_product = np.trace(np.dot(current_rot.T, target.orientation))
                        similarity = (dot_product - 1) / 2.0
                        orientation_reward = max(0.0, similarity)
                    else:
                        orientation_reward = 0.0
                    total_orientation_reward += target.weight * orientation_reward

            except Exception as e:
                if self.debug:
                    print(f"Error processing body {body_name}: {e}")
                continue

        position_reward = total_position_reward / total_effective_weight if total_effective_weight > 0 else 0.0
        orientation_reward = total_orientation_reward / total_effective_weight if total_effective_weight > 0 else 0.0

        ctrl = data.ctrl.copy()
        control_reward = rewards.tolerance(
            np.linalg.norm(ctrl),
            bounds=(0, 1),
            margin=1,
            value_at_margin=0,
            sigmoid="quadratic"
        )
        control_reward = control_reward.item() if hasattr(control_reward, 'item') else float(control_reward)

        #upright = get_chest_upright(model, data)
        #upright_reward = upright.item() if hasattr(upright, 'item') else float(upright)

        remaining_weight = 1.0 - self.control_weight - self.orientation_weight
        final_reward = (
            remaining_weight * position_reward +
            self.orientation_weight * orientation_reward +
            self.control_weight * control_reward 
            #self.upright_weight * upright_reward
        )

        if self.debug:
            print("--- Reward Breakdown ---")
            print(f"Position Reward: {position_reward:.4f} (Weight: {remaining_weight:.2f})")
            print(f"Orientation Reward: {orientation_reward:.4f} (Weight: {self.orientation_weight:.2f})")
            print(f"Control Reward: {control_reward:.4f} (Weight: {self.control_weight:.2f})")
            #print(f"Upright Reward: {upright_reward:.4f} (Weight: {self.upright_weight:.2f})")
            print(f"Final Reward: {final_reward:.4f}")

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

    def get_serialized_targets(self) -> Dict[str, Dict[str, float]]:
        """
        Get a serialized dictionary of all target positions and their parameters.
        
        Returns:
            Dict with format:
            {
                "body_name": {
                    "x": float or None,
                    "y": float or None,
                    "z": float or None,
                    "weight": float,
                    "margin": float,
                    "sigmoid": str
                },
                ...
            }
        """
        serialized = {}
        for body_name, target in self.targets.items():
            serialized[body_name] = {
                "x": target.x,
                "y": target.y,
                "z": target.z,
                "weight": target.weight,
                "margin": target.margin,
                "sigmoid": target.sigmoid
            }
        return serialized

    def get_current_positions(self, model: mujoco.MjModel, data: mujoco.MjData) -> Dict[str, Dict[str, float]]:
        """
        Get current positions of all target bodies in both global and local frames.
        
        Returns:
            Dict with format:
            {
                "body_name": {
                    "global": {"x": float, "y": float, "z": float},
                    "local": {"x": float, "y": float, "z": float}  # Only if use_local_frame is True
                },
                ...
            }
        """
        positions = {}
        
        # Get reference frame data
        pelvis_pos = data.xpos[model.body("Pelvis").id].copy()
        pelvis_rotation = get_rotation_matrix_from_pelvis(model, data) if self.use_local_frame else np.eye(3)
        
        for body_name in self.targets.keys():
            current_pos = data.xpos[model.body(body_name).id].copy()
            
            position_data = {
                "global": {
                    "x": float(current_pos[0]),
                    "y": float(current_pos[1]),
                    "z": float(current_pos[2])
                }
            }
            
            if self.use_local_frame:
                local_pos = transform_point_to_local_frame(current_pos, pelvis_pos, pelvis_rotation)
                position_data["local"] = {
                    "x": float(local_pos[0]),
                    "y": float(local_pos[1]),
                    "z": float(local_pos[2])
                }
            
            positions[body_name] = position_data
            
        return positions
        
    def get_reward_breakdown(self, model: mujoco.MjModel, data: mujoco.MjData) -> Dict[str, float]:
        """
        Get a detailed breakdown of the reward components.
        
        Returns:
            Dict with format:
            {
                "total": float,
                "position": float,
                "control": float,
                "body_parts": {
                    "body_name": float,
                    ...
                }
            }
        """
        # Position rewards
        body_rewards = {}
        total_position_reward = 0.0
        total_effective_weight = 0.0

        # Get the humanoid's reference frame if we're using local coordinates
        pelvis_pos = data.xpos[model.body("Pelvis").id].copy()
        pelvis_rotation = get_rotation_matrix_from_pelvis(model, data) if self.use_local_frame else np.eye(3)

        for body_name, target in self.targets.items():
            # Get the current position of the body part
            try:
                current_pos = data.xpos[model.body(body_name).id].copy()
                
                # Don't calculate reward for Pelvis if using local frame, it's always [0,0,0]
                if self.use_local_frame and body_name == "Pelvis":
                    continue
    
                # Transform to local coordinates if needed
                if self.use_local_frame:
                    current_pos = transform_point_to_local_frame(current_pos, pelvis_pos, pelvis_rotation)
    
                axis_rewards = []
    
                # Check each axis
                for i, (axis_val, target_val) in enumerate([
                    (current_pos[0], target.x),
                    (current_pos[1], target.y),
                    (current_pos[2], target.z)
                ]):
                    if target_val is not None:
                        reward = rewards.tolerance(
                            axis_val,
                            bounds=(target_val - target.margin, target_val + target.margin),
                            margin=target.margin,
                            value_at_margin=0.01,
                            sigmoid=target.sigmoid
                        )
                        reward = reward.item() if hasattr(reward, 'item') else float(reward)
                        axis_rewards.append(reward)
    
                if axis_rewards:
                    body_reward = np.mean(axis_rewards)
                    body_rewards[body_name] = float(body_reward)
                    total_position_reward += target.weight * body_reward
                    total_effective_weight += target.weight
            except Exception as e:
                if self.debug:
                    print(f"Error processing body {body_name}: {e}")
                continue

        # Use the weighted sum directly instead of normalizing
        position_reward = total_position_reward

        # Compute control cost
        ctrl = data.ctrl.copy()
        control_reward = rewards.tolerance(
            np.linalg.norm(ctrl),
            bounds=(0, 1),
            margin=1,
            value_at_margin=0,
            sigmoid="quadratic"
        )
        control_reward = control_reward.item() if hasattr(control_reward, 'item') else float(control_reward)

        # Combine rewards: Normalize position and control weights
        pos_weight = 1.0 - self.control_weight
        ctrl_weight = self.control_weight

        final_reward = (
            pos_weight * position_reward +
            ctrl_weight * control_reward
        )

        return {
            "total": float(final_reward),
            "position": float(position_reward),
            "control": float(control_reward),
            "body_parts": body_rewards
        } 