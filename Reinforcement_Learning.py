# -*- coding: utf-8 -*-
"""
Created on Wed Jan 10 18:12:20 2018

@author: Administrator
"""

import tensorflow as tf
import numpy as np

import tflearn
import argparse
import pprint as pp
from collections import deque
import random

import matplotlib.pyplot as plt

class ReplayBuffer(object):

    def __init__(self, buffer_size, random_seed=123):
        """
        The right side of the deque contains the most recent experiences 
        """
        self.buffer_size = buffer_size
        self.count = 0
        self.buffer = deque()
        random.seed(random_seed)

    def add(self, s, a, r, t, s2):
        experience = (s, a, r, t, s2)
        if self.count < self.buffer_size: 
            self.buffer.append(experience)
            self.count += 1
        else:
            self.buffer.popleft()
            self.buffer.append(experience)

    def size(self):
        return self.count

    def sample_batch(self, batch_size):
        batch = []

        if self.count < batch_size:
            batch = random.sample(self.buffer, self.count)
        else:
            batch = random.sample(self.buffer, batch_size)

        s_batch = np.array([_[0] for _ in batch])
        a_batch = np.array([_[1] for _ in batch])
        r_batch = np.array([_[2] for _ in batch])
        t_batch = np.array([_[3] for _ in batch])
        s2_batch = np.array([_[4] for _ in batch])

        return s_batch, a_batch, r_batch, t_batch, s2_batch

    def clear(self):
        self.buffer.clear()
        self.count = 0

class Controler(object):
    def __init__(self, rel_r=0.1):
        	#constant var
        	self.det_t = 0.01
        	self.g = 9.8
        	self.m = 0.226
        	self.R = 0.0380
        	self.K = 0.484
        	self.I_beam = 0.0271
        	self.b = 0.066
        	self.I_ball = 0.4*self.m*self.R*self.R
        	self.tmp = self.m + self.I_ball/(self.R*self.R)
        	#variable var
        	#self.V = 0
        	self.r = rel_r
        	self.theta = 0
        	self.r_dot = 0
        	self.theta_dot = 0
        	self.det_r_dot = 0
        	self.det_theta_dot = 0
        	self.state = [self.r, self.theta, self.r_dot, self.theta_dot]
        	#list for plot
        	self.r_list = []
        	self.theta_list = []
        	#about train
        	self._step = 0
        	self.done = False
        	self.reward = 0

    def reset(self, rel_r=0.1):
        	self.r = rel_r
        	self.theta = 0
        	self.r_dot = 0
        	self.theta_dot = 0
        	self.det_r_dot = 0
        	self.det_theta_dot = 0
        	#self.V = 0
        	self.state = [self.r, self.theta, self.r_dot, self.theta_dot]
    
        	self.r_list = []
        	self.theta_list = []
    
        	self._step = 0
        	self.done = False
        	self.reward = 0
    
        	return [rel_r, 0., 0., 0.]

    def step(self, V):
        	tmp_1 = (self.I_beam+self.m*self.r*self.r+self.b+\
        		2*self.m*self.r*self.r_dot+self.b*self.theta_dot+\
        		2*self.m*self.r*self.theta_dot*self.m*self.r*2*self.theta_dot/self.tmp)
        	tmp_2 = self.m*self.r*self.theta_dot*self.theta_dot-self.m*self.g*np.sin(self.theta)
        	tmp_3 = 2*self.m*self.r*self.theta_dot*self.r_dot-\
        		self.K*V+2*self.m*self.r*self.theta_dot*tmp_2/self.tmp
        	tmp_4 = tmp_2/self.tmp
        	tmp_5 = self.m*self.r*2*self.theta_dot/self.tmp
    
        	self.det_theta_dot = -tmp_3/tmp_1
        	self.det_r_dot = tmp_5*self.det_theta_dot+tmp_4
        	self.r_dot = self.r_dot+self.det_r_dot
        	self.theta_dot = self.theta_dot+self.det_theta_dot
        	self.r = self.r+self.det_t*self.r_dot
        	self.theta = self.theta+self.det_t*self.theta_dot
        	self.state = [self.r, self.theta, self.r_dot, self.theta_dot]

        	self._step += 1
        
        	if abs(self.r) > 1:
        		self.done = True
        	if abs(self.theta) > np.pi/2:
        		self.done = True
        	if self._step > 10000:
        		self.done = True
        	#this is most important
        	self.reward = 1-abs(self.r)+2/np.pi*(np.pi/2-abs(self.theta))
        	if self.reward < 0:
        		self.reward = 0
        	#print(self._step,':',self.r)
        	return self.state, self.reward, self.done
    
##############################################################

# ===========================
#   Actor and Critic DNNs
# ===========================

class ActorNetwork(object):
    """
    Input to the network is the state, output is the action
    under a deterministic policy.
    The output layer activation is a tanh to keep the action
    between -action_bound and action_bound
    """

    def __init__(self, sess, state_dim, action_dim, action_bound, learning_rate, tau, batch_size):
        self.sess = sess
        self.s_dim = state_dim
        self.a_dim = action_dim
        self.action_bound = action_bound
        self.learning_rate = learning_rate
        self.tau = tau
        self.batch_size = batch_size

        # Actor Network
        self.inputs, self.out, self.scaled_out = self.create_actor_network()

        self.network_params = tf.trainable_variables()

        # Target Network
        self.target_inputs, self.target_out, self.target_scaled_out = self.create_actor_network()

        self.target_network_params = tf.trainable_variables()[
            len(self.network_params):]

        # Op for periodically updating target network with online network
        # weights
        self.update_target_network_params = \
            [self.target_network_params[i].assign(tf.multiply(self.network_params[i], self.tau) +
                tf.multiply(self.target_network_params[i], 1. - self.tau))
                for i in range(len(self.target_network_params))]

        # This gradient will be provided by the critic network
        self.action_gradient = tf.placeholder(tf.float32, [None, self.a_dim])

        # Combine the gradients here
        self.unnormalized_actor_gradients = tf.gradients(
            self.scaled_out, self.network_params, -self.action_gradient)
        self.actor_gradients = list(map(lambda x: tf.div(x, self.batch_size), self.unnormalized_actor_gradients))

        # Optimization Op
        self.optimize = tf.train.AdamOptimizer(self.learning_rate).\
            apply_gradients(zip(self.actor_gradients, self.network_params))

        self.num_trainable_vars = len(
            self.network_params) + len(self.target_network_params)

    def create_actor_network(self):
        inputs = tflearn.input_data(shape=[None, self.s_dim])
        net = tflearn.fully_connected(inputs, 400, activation=lambda x: tflearn.activations.leaky_relu(x, alpha=0.2))
        #net = tflearn.layers.normalization.batch_normalization(net)
        net = tflearn.local_response_normalization(net)
        #net = tflearn.fully_connected(net, 600,activation='relu', regularizer='L1', decay=0.001)
        net = tflearn.fully_connected(net, 600,activation=lambda x: tflearn.activations.leaky_relu(x, alpha=0.2), regularizer='L1', decay=0.001)
        #net = tflearn.dropout(net, 0.7)
        net = tflearn.fully_connected(net, 300,activation=lambda x: tflearn.activations.leaky_relu(x, alpha=0.2),  regularizer='L1', decay=0.001)
        #net = tflearn.local_response_normalization(net)
        # Final layer weights are init to Uniform[-3e-3, 3e-3]
        w_init = tflearn.initializations.uniform(minval=-0.003, maxval=0.003)
        out = tflearn.fully_connected(
            net, self.a_dim, activation='tanh', weights_init=w_init)
        # Scale output to -action_bound to action_bound
        scaled_out = tf.multiply(out, self.action_bound)
        return inputs, out, scaled_out

    def train(self, inputs, a_gradient):
        self.sess.run(self.optimize, feed_dict={
            self.inputs: inputs,
            self.action_gradient: a_gradient
        })

    def predict(self, inputs):
        return self.sess.run(self.scaled_out, feed_dict={
            self.inputs: inputs
        })

    def predict_target(self, inputs):
        return self.sess.run(self.target_scaled_out, feed_dict={
            self.target_inputs: inputs
        })

    def update_target_network(self):
        self.sess.run(self.update_target_network_params)

    def get_num_trainable_vars(self):
        return self.num_trainable_vars


class CriticNetwork(object):
    """
    Input to the network is the state and action, output is Q(s,a).
    The action must be obtained from the output of the Actor network.
    """

    def __init__(self, sess, state_dim, action_dim, learning_rate, tau, gamma, num_actor_vars):
        self.sess = sess
        self.s_dim = state_dim
        self.a_dim = action_dim
        self.learning_rate = learning_rate
        self.tau = tau
        self.gamma = gamma

        # Create the critic network
        self.inputs, self.action, self.out = self.create_critic_network()

        self.network_params = tf.trainable_variables()[num_actor_vars:]

        # Target Network
        self.target_inputs, self.target_action, self.target_out = self.create_critic_network()

        self.target_network_params = tf.trainable_variables()[(len(self.network_params) + num_actor_vars):]

        # Op for periodically updating target network with online network
        # weights with regularization
        self.update_target_network_params = \
            [self.target_network_params[i].assign(tf.multiply(self.network_params[i], self.tau) \
            + tf.multiply(self.target_network_params[i], 1. - self.tau))
                for i in range(len(self.target_network_params))]

        # Network target (y_i)
        self.predicted_q_value = tf.placeholder(tf.float32, [None, 1])

        # Define loss and optimization Op
        self.loss = tflearn.mean_square(self.predicted_q_value, self.out)
        self.optimize = tf.train.AdamOptimizer(
            self.learning_rate).minimize(self.loss)

        # Get the gradient of the net w.r.t. the action.
        # For each action in the minibatch (i.e., for each x in xs),
        # this will sum up the gradients of each critic output in the minibatch
        # w.r.t. that action. Each output is independent of all
        # actions except for one.
        self.action_grads = tf.gradients(self.out, self.action)

    def create_critic_network(self):
        inputs = tflearn.input_data(shape=[None, self.s_dim])
        action = tflearn.input_data(shape=[None, self.a_dim])
        net = tflearn.fully_connected(net, 400,activation=lambda x: tflearn.activations.leaky_relu(x, alpha=0.2),  regularizer='L1', decay=0.001)
        net = tflearn.fully_connected(net, 600,activation=lambda x: tflearn.activations.leaky_relu(x, alpha=0.2),  regularizer='L1', decay=0.001)
        net = tflearn.fully_connected(net, 300,activation=lambda x: tflearn.activations.leaky_relu(x, alpha=0.2),  regularizer='L1', decay=0.001)
        #net = tflearn.fully_connected(inputs, 400)
        #net = tflearn.layers.normalization.batch_normalization(net)
        #net = tflearn.activations.relu(net)
        #net = tflearn.fully_connected(net, 400)##############
        #net = tflearn.layers.normalization.batch_normalization(net)
        #net = tflearn.activations.relu(net)
        #net = tflearn.fully_connected(net, 300)##########
        #net = tflearn.layers.normalization.batch_normalization(net)
        #net = tflearn.activations.relu(net)
        
        # Add the action tensor in the 2nd hidden layer
        # Use two temp layers to get the corresponding weights and biases
        t1 = tflearn.fully_connected(net, 300)
        t2 = tflearn.fully_connected(action, 300)

        net = tflearn.activation(
            tf.matmul(net, t1.W) + tf.matmul(action, t2.W) + t2.b, activation=lambda x: tflearn.activations.leaky_relu(x, alpha=0.2))

        # linear layer connected to 1 output representing Q(s,a)
        # Weights are init to Uniform[-3e-3, 3e-3]
        w_init = tflearn.initializations.uniform(minval=-0.003, maxval=0.003)
        out = tflearn.fully_connected(net, 1, weights_init=w_init)
        return inputs, action, out

    def train(self, inputs, action, predicted_q_value):
        return self.sess.run([self.out, self.optimize], feed_dict={
            self.inputs: inputs,
            self.action: action,
            self.predicted_q_value: predicted_q_value
        })

    def predict(self, inputs, action):
        return self.sess.run(self.out, feed_dict={
            self.inputs: inputs,
            self.action: action
        })

    def predict_target(self, inputs, action):
        return self.sess.run(self.target_out, feed_dict={
            self.target_inputs: inputs,
            self.target_action: action
        })

    def action_gradients(self, inputs, actions):
        return self.sess.run(self.action_grads, feed_dict={
            self.inputs: inputs,
            self.action: actions
        }) 

    def update_target_network(self):
        self.sess.run(self.update_target_network_params)

        
# Taken from https://github.com/openai/baselines/blob/master/baselines/ddpg/noise.py, which is
# based on http://math.stackexchange.com/questions/1287634/implementing-ornstein-uhlenbeck-in-matlab
class OrnsteinUhlenbeckActionNoise:
    def __init__(self, mu, sigma=0.3, theta=1.00, dt=1e-2, x0=None):
        self.theta = theta
        self.mu = mu
        self.sigma = sigma
        self.dt = dt
        self.x0 = x0
        self.reset()

    def __call__(self):
        x = self.x_prev + self.theta * (self.mu - self.x_prev) * self.dt + \
                self.sigma * np.sqrt(self.dt) * np.random.normal(size=self.mu.shape)
        self.x_prev = x
        return x

    def reset(self):
        self.x_prev = self.x0 if self.x0 is not None else np.zeros_like(self.mu)

    def __repr__(self):
        return 'OrnsteinUhlenbeckActionNoise(mu={}, sigma={})'.format(self.mu, self.sigma)

# ===========================
#   Tensorflow Summary Ops
# ===========================

def build_summaries():
    episode_reward = tf.Variable(0.)
    tf.summary.scalar("Reward", episode_reward)
    episode_max_step = tf.Variable(0.)
    tf.summary.scalar("Max Step", episode_max_step)
    episode_ave_max_q = tf.Variable(0.)
    tf.summary.scalar("Qmax Value", episode_ave_max_q)

    summary_vars = [episode_reward, episode_max_step, episode_ave_max_q]
    summary_ops = tf.summary.merge_all()

    return summary_ops, summary_vars

# ===========================
#   Agent Training
# ===========================

#def train(sess, env, args, actor, critic, actor_noise):
def train(sess, args, actor, critic, actor_noise):
    # Set up summary Ops
    summary_ops, summary_vars = build_summaries()
    sess.run(tf.global_variables_initializer())
    writer = tf.summary.FileWriter(args['summary_dir'], sess.graph)
    # Initialize target network weights
    actor.update_target_network()
    critic.update_target_network()
    # Initialize replay memory
    replay_buffer = ReplayBuffer(int(args['buffer_size']), int(args['random_seed']))
    
    ####### create an object ###############
    ctrl = Controler()

    for i in range(int(args['max_episodes'])):
        s = ctrl.reset()
        ep_reward = 0
        ep_ave_max_q = 0
        for j in range(int(args['max_episode_len'])):

            # Added exploration noise
            a = actor.predict(np.reshape(s, (1, actor.s_dim))) + actor_noise()
            #print('a:',a)
            s2, reward, done = ctrl.step(a[0])
            if reward < 0:
                reward = 0
            #print('\ns2:',s2,'\nreward:',reward,'\ndone:',done)
            replay_buffer.add(np.reshape(s, (actor.s_dim,)), np.reshape(a, (actor.a_dim,)), reward,
                              done, np.reshape(s2, (actor.s_dim,)))
            # Keep adding experience to the memory until
            # there are at least minibatch size samples
            if replay_buffer.size() > int(args['minibatch_size']):
                s_batch, a_batch, r_batch, t_batch, s2_batch = \
                    replay_buffer.sample_batch(int(args['minibatch_size']))
                # Calculate targets
                target_q = critic.predict_target(
                    s2_batch, actor.predict_target(s2_batch))
                y_i = []
                for k in range(int(args['minibatch_size'])):
                    if t_batch[k]:
                        y_i.append(r_batch[k])
                    else:
                        y_i.append(r_batch[k] + critic.gamma * target_q[k])
                # Update the critic given the targets
                predicted_q_value, _ = critic.train(
                    s_batch, a_batch, np.reshape(y_i, (int(args['minibatch_size']), 1)))
                ep_ave_max_q += np.amax(predicted_q_value)
                # Update the actor policy using the sampled gradient
                a_outs = actor.predict(s_batch)
                grads = critic.action_gradients(s_batch, a_outs)
                actor.train(s_batch, grads[0])
                # Update target networks
                actor.update_target_network()
                critic.update_target_network()
                
            s = s2
            ep_reward += reward
            if done:
                f.write(str(ep_reward)[1:-1]+'\n')
                f2.write(str(ctrl._step)+'\n')
                print('max step:',ctrl._step)

                summary_str = sess.run(summary_ops, feed_dict={
                    summary_vars[0]: ep_reward[0],
                    summary_vars[1]: ctrl._step,
                    summary_vars[2]: ep_ave_max_q / float(j),
                })
                writer.add_summary(summary_str, i)
                writer.flush()
                print('| Reward: {:d} | Episode: {:d} | Qmax: {:.4f}'.format(int(ep_reward), \
                        i, (ep_ave_max_q / float(j))))
                rwd.append(ep_reward)
                max_step.append(ctrl._step)
                break

def main(args):
    with tf.Session() as sess:
        #env = gym.make(args['env'])
        np.random.seed(int(args['random_seed']))
        tf.set_random_seed(int(args['random_seed']))
        state_dim = 4
        action_dim = 1
        action_bound = [ 25.0 ]
        actor = ActorNetwork(sess, state_dim, action_dim, action_bound,
                             float(args['actor_lr']), float(args['tau']),
                             int(args['minibatch_size']))

        critic = CriticNetwork(sess, state_dim, action_dim,
                               float(args['critic_lr']), float(args['tau']),
                               float(args['gamma']),
                               actor.get_num_trainable_vars())
        actor_noise = OrnsteinUhlenbeckActionNoise(mu=np.zeros(action_dim))

        train(sess, args, actor, critic, actor_noise)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='provide arguments for DDPG agent')

    # agent parameters
    parser.add_argument('--actor-lr', help='actor network learning rate', default=0.0001)
    parser.add_argument('--critic-lr', help='critic network learning rate', default=0.001)
    parser.add_argument('--gamma', help='discount factor for critic updates', default=0.999)
    parser.add_argument('--tau', help='soft target update parameter', default=0.001)
    parser.add_argument('--buffer-size', help='max size of the replay buffer', default=1000000)
    parser.add_argument('--minibatch-size', help='size of minibatch for minibatch-SGD', default=64)

    # run parameters
    parser.add_argument('--env', help='train {Ball-Beam}', default='Ball-Beam')
    parser.add_argument('--random-seed', help='random seed for repeatability', default=1234)
    parser.add_argument('--max-episodes', help='max num of episodes to do while training', default=500000)###
    parser.add_argument('--max-episode-len', help='max length of 1 episode', default=10000)
    parser.add_argument('--summary-dir', help='directory for storing tensorboard info', default='./results/tf_ddpg')

    parser.set_defaults(render_env=True)
    parser.set_defaults(use_gym_monitor=False)

    args = vars(parser.parse_args())
    
    pp.pprint(args)
    rwd = []
    max_step = []
    f = open('reward.txt', "w+")
    f2 = open('step.txt', "w+")
    main(args)
    t = [i for i in range(len(rwd))]
    plt.plot(t, rwd)
    plt.plot(t, max_step)
    f.close()
    f2.close()