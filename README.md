# DRL
Deep Reinforcement Learning
```python
net = tflearn.fully_connected(net, 600,activation=lambda x: tflearn.activations.leaky_relu(x, alpha=0.2), regularizer='L1', decay=0.001)
```
Use **leaky_relu** instead of relu
Use **L1 regularization** to make the model more simple
