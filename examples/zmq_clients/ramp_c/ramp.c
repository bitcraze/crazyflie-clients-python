#include <zmq.h>
#include <string.h>
#include <stdio.h>
#include <unistd.h>

char * messageFmt = "{" \
    "\"version\": 1," \
    "\"client_name\": \"ramp C example\"," \
    "\"ctrl\": {" \
        "\"roll\": 0.0," \
        "\"pitch\": 0.0," \
        "\"yaw\": 0.0," \
        "\"thrust\": %f" \
    "}" \
"}";
char message[512];

int main()
{
  void *context;
  void *socket_zmq;
  const char *address;
  context = zmq_ctx_new();
  socket_zmq = zmq_socket(context, ZMQ_PUSH);
  address = "tcp://127.0.0.1:1212";

  printf("Connecting the socket ...\n");
  zmq_connect(socket_zmq, address);

  printf("Sending input commands ...\n");
  for (float thrust=0; thrust < 30.1; thrust += 2) {
    sprintf(message, messageFmt, thrust);
    zmq_send(socket_zmq, message, strlen(message), 0);
    printf("\rThrust = %f%%", thrust);
    fflush(stdout);
    sleep(1);
  }

  sprintf(message, messageFmt, 0);
  zmq_send(socket_zmq, message, strlen(message), 0);
  printf("\rThrust = %f%%\n", 0.0);

  zmq_close(socket_zmq);
  zmq_ctx_destroy(context);

  return 0;
}
