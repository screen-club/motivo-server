import torch
import numpy as np
from humenv import make_humenv
from gymnasium.wrappers import FlattenObservation, TransformObservation, TimeLimit

def setup_environment(device="cpu", max_steps=2000000):
    """Setup basic environment with humanoid"""
    env, _ = make_humenv(
        num_envs=1,
        wrappers=[
            FlattenObservation,
            lambda env: TransformObservation(
                env, 
                lambda obs: torch.tensor(obs.reshape(1, -1), 
                                      dtype=torch.float32, 
                                      device=device),
                env.observation_space
            ),
        ],
    )
    
    # Set up physics parameters
    unwrapped_env = env.unwrapped
    unwrapped_env.model.opt.density = 1.2
    unwrapped_env.model.opt.wind = np.array([0., 0., 0.])
    unwrapped_env.model.opt.viscosity = 0.0
    unwrapped_env.model.opt.integrator = 0
    unwrapped_env.model.opt.timestep = 0.002
    
    return TimeLimit(env, max_episode_steps=max_steps) 