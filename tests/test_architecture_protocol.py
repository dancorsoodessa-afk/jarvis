from agent.protocol import PROTOCOL_VERSION, request, validate
from agent.state import JarvisState, StateMachine

def test_protocol_envelope_and_validation():
    msg=request(7,"message",text="привет")
    assert msg["protocol"]==PROTOCOL_VERSION and msg["id"]==7 and msg["type"]=="message"
    validate(msg)

def test_state_machine_is_single_source_of_truth():
    sm=StateMachine(); seen=[]; sm.subscribe(lambda old,new: seen.append((old,new)))
    sm.thinking(); sm.executing(); sm.speaking(); sm.idle()
    assert sm.state is JarvisState.IDLE
    assert [x[1] for x in seen]==[JarvisState.THINKING,JarvisState.EXECUTING,JarvisState.SPEAKING,JarvisState.IDLE]
