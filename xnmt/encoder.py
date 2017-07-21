import dynet as dy
import residual
import model_globals

# The LSTM model builders
import pyramidal
import conv_encoder
import segmenting_encoder

# ETC
from embedder import ExpressionSequence
from translator import TrainTestInterface
from serializer import Serializable

class Encoder(TrainTestInterface):
  """
  An Encoder is a class that takes an ExpressionSequence as input and outputs another encoded ExpressionSequence.
  """

  def transduce(self, sent):
    """Encode inputs representing a sequence of continuous vectors into outputs that also represent a sequence of continuous vectors.

    :param sent: The input to be encoded. In the great majority of cases this will be an ExpressionSequence.
      It can be something else if the encoder is over something that is not a sequence of vectors though.
    :returns: The encoded output. In the great majority of cases this will be an ExpressionSequence.
      It can be something else if the encoder is over something that is not a sequence of vectors though.
    """
    raise NotImplementedError('Unimplemented transduce for class:', self.__class__.__name__)

  def set_train(self, val):
    raise NotImplementedError("Unimplemented set_train for class:", self.__class__.__name__)

  def calc_reinforce_loss(self, reward):
    return None

class BuilderEncoder(Encoder):
  def transduce(self, sent):
    return ExpressionSequence(expr_list=self.builder.transduce(sent))

class IdentityEncoder(Encoder, Serializable):
  yaml_tag = u'!IdentityEncoder'

  def transduce(self, sent):
    return ExpressionSequence(expr_list = sent)

  def set_train(self, val): pass

class LSTMEncoder(BuilderEncoder, Serializable):
  yaml_tag = u'!LSTMEncoder'

  def __init__(self, input_dim=None, layers=1, hidden_dim=None, dropout=None, bidirectional=True):
    model = model_globals.dynet_param_collection.param_col
    input_dim = input_dim or model_globals.get("default_layer_dim")
    hidden_dim = hidden_dim or model_globals.get("default_layer_dim")
    dropout = dropout or model_globals.get("dropout")
    self.input_dim = input_dim
    self.layers = layers
    self.hidden_dim = hidden_dim
    self.dropout = dropout
    if bidirectional:
      self.builder = dy.BiRNNBuilder(layers, input_dim, hidden_dim, model, dy.VanillaLSTMBuilder)
    else:
      self.builder = dy.VanillaLSTMBuilder(layers, input_dim, hidden_dim, model)

  def set_train(self, val):
    self.builder.set_dropout(self.dropout if val else 0.0)

class ResidualLSTMEncoder(BuilderEncoder, Serializable):
  yaml_tag = u'!ResidualLSTMEncoder'

  def __init__(self, input_dim=512, layers=1, hidden_dim=None, residual_to_output=False, dropout=None, bidirectional=True):
    model = model_globals.dynet_param_collection.param_col
    hidden_dim = hidden_dim or model_globals.get("default_layer_dim")
    dropout = dropout or model_globals.get("dropout")
    self.dropout = dropout
    if bidirectional:
      self.builder = residual.ResidualBiRNNBuilder(layers, input_dim, hidden_dim, model, dy.VanillaLSTMBuilder, residual_to_output)
    else:
      self.builder = residual.ResidualRNNBuilder(layers, input_dim, hidden_dim, model, dy.VanillaLSTMBuilder, residual_to_output)

  def set_train(self, val):
    self.builder.set_dropout(self.dropout if val else 0.0)

class PyramidalLSTMEncoder(BuilderEncoder, Serializable):
  yaml_tag = u'!PyramidalLSTMEncoder'

  def __init__(self, input_dim=512, layers=1, hidden_dim=None, downsampling_method="skip", reduce_factor=2, dropout=None):
    hidden_dim = hidden_dim or model_globals.get("default_layer_dim")
    dropout = dropout or model_globals.get("dropout")
    self.dropout = dropout
    self.builder = pyramidal.PyramidalRNNBuilder(layers, input_dim, hidden_dim,
                                                 model_globals.dynet_param_collection.param_col, dy.VanillaLSTMBuilder,
                                                 downsampling_method, reduce_factor)

  def set_train(self, val):
    self.builder.set_dropout(self.dropout if val else 0.0)

class ConvBiRNNBuilder(BuilderEncoder, Serializable):
  yaml_tag = u'!ConvBiRNNBuilder'

  def init_builder(self, input_dim, layers, hidden_dim=None, chn_dim=3, num_filters=32, filter_size_time=3, filter_size_freq=3, stride=(2,2), dropout=None):
    model = model_globals.dynet_param_collection.param_col
    hidden_dim = hidden_dim or model_globals.get("default_layer_dim")
    dropout = dropout or model_globals.get("dropout")
    self.dropout = dropout
    self.builder = conv_encoder.ConvBiRNNBuilder(layers, input_dim, hidden_dim, model, dy.VanillaLSTMBuilder,
                                                 chn_dim, num_filters, filter_size_time, filter_size_freq,
                                                 stride)

  def set_train(self, val):
    self.builder.set_dropout(self.dropout if val else 0.0)

class ModularEncoder(Encoder, Serializable):
  yaml_tag = u'!ModularEncoder'

  def __init__(self, input_dim, modules):
    self.modules = modules

  def shared_params(self):
    return [set(["input_dim", "modules.0.input_dim"])]

  def transduce(self, sent):
    for module in self.modules:
      sent = module.transduce(sent)
    return sent

  def get_train_test_components(self):
    return self.modules

  def set_train(self, val):
    for module in self.modules:
      module.set_train(val)

class SegmentingEncoder(Encoder, Serializable):
  yaml_tag = u'!SegmentingEncoder'

  def __init__(self, embed_encoder=None, segment_transducer=None, lmbd=None):
    model = model_globals.dynet_param_collection.param_col

    self.ctr = 0
    self.lmbd_val = lmbd["start"]
    self.lmbd     = lmbd
    self.builder = segmenting_encoder.SegmentingEncoderBuilder(embed_encoder, segment_transducer, model)

  def transduce(self, sent):
    return ExpressionSequence(expr_tensor=self.builder.transduce(sent))

  def set_train(self, val):
    self.builder.set_train(val)

  def calc_reinforce_loss(self, reward):
    return self.builder.calc_reinforce_loss(reward, self.lmbd_val)

  def new_epoch(self):
    self.ctr += 1
#    self.lmbd_val *= self.lmbd["multiplier"]
    self.lmbd_val = 1e-3 * ((2 ** self.ctr) - 10)
    self.lmbd_val = min(self.lmbd_val, self.lmbd["max"])
    self.lmbd_val = max(self.lmbd_val, self.lmbd["min"])

    print("Now lambda:", self.lmbd_val)

